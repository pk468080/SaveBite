"""W9.1.3 — Razorpay webhook security + payment/reservation race validation.

Stage D (webhook HTTP handler) and Stage E (payment/expiry races) against
the REAL FastAPI endpoint, REAL PostgREST, and REAL PostgreSQL 17. The only
substituted component is the Razorpay provider itself: there are no valid
test-mode credentials and no approved staging environment (Stage A), so the
provider is a scripted fake returning canned provider dicts. Every webhook
request in this module is LOCALLY GENERATED and HMAC-signed with a
throwaway, per-session test secret — NEVER a genuine Razorpay-delivered
webhook. Real-provider API testing is BLOCKED (see Stage F in
docs/w9-1-3-staging-validation.md); nothing here claims otherwise.

Test-environment deviations (documented, disposable setup only):
  * The migration chain never grants USAGE ON SCHEMA private to
    service_role, so the public backend_* wrappers (all SECURITY INVOKER)
    cannot be invoked through PostgREST at all — the first smoke call
    failed with 403 "permission denied for schema private". The
    pg17_session fixture applies that single GRANT in the disposable test
    database only, which unblocks the real PostgREST path and proves the
    proposed fix. The grant is NOT applied to production, NOT added to
    any migration in this branch, and is proposed as a separate
    forward-only migration in docs/w9-1-3-staging-validation.md. Without
    it, every test below fails at the first RPC call — that failure IS
    the defect report, not a harness problem.
  * The app's Supabase client targets Supabase's URL layout
    ({supabase_url}/rest/v1/rpc/...), but standalone PostgREST serves at
    its root (/rpc/...). The postgrest_session fixture therefore starts
    a test-only stdlib reverse proxy that strips the /rest/v1 prefix —
    exactly the routing Supabase's Kong layer performs in production.
    App code, PostgREST, and PostgreSQL are all real; only the
    production routing prefix is emulated, and it is labelled here.
  * The sandbox's proxy environment breaks httpx client construction
    (its NO_PROXY list contains bare IPv6 entries httpx cannot parse as
    URL patterns: InvalidURL "Invalid port"). The api_client fixture
    therefore removes the proxy variables for the duration of each test
    and restores them afterwards. This is a sandbox quirk, not a product
    defect: production (Vercel) has no such proxy environment, and the
    handler's own upstream-error mapping is unchanged.

Run prerequisites (fail clearly when missing, never silently mocked):
  1. A disposable PostgreSQL 17 cluster bootstrapped with
     backend/tests/pg_bootstrap.py (W9.1.2 script), e.g.::
       PATH=/usr/lib/postgresql/17/bin:$PATH python3 backend/tests/pg_bootstrap.py \\
         --pgdata /tmp/savebite-pgtest17/data --socket-dir /tmp/savebite-pgtest17/sock \\
         --port 54400
  2. A PostgREST binary (this fixture starts it itself). Download when missing:
     https://github.com/PostgREST/postgrest/releases/download/v12.2.3/postgrest-v12.2.3-linux-static-x64.tar.xz
     (verified 12.2.3 for this run; place it at /tmp/postgrest/postgrest or
     set SAVEBITE_POSTGREST_BIN).
  3. DSN override: SAVEBITE_PG_TEST_DSN (default: the PG 17 socket above).
     The fixture REFUSES a non-17 server so a run can never silently test
     another version while claiming 17.

Pure helpers (fixtures, barrier, observation, invariants) are imported from
the W9.1.2 suite; fixtures do not cross modules, so this module defines
its own (pg17_session, postgrest_session, db_conn, api_client).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import os
import secrets
import socket
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import ProxyHandler, build_opener

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.dependencies import get_razorpay_client, get_service_client
from app.errors import BadGatewayError
from app.main import create_app
from app.supabase_client import service_client
from tests.test_pg_concurrency import (
    TABLES_TRUNCATE,
    assert_invariants,
    backend_pid,
    call_cleanup,
    count_events,
    count_order_events,
    fetch_listing,
    fetch_order,
    fetch_tx,
    install_barrier_objects,
    locks_for,
    make_fixture,
    set_barrier,
    wait_blocked,
    wait_until,
)

BARRIER_KEY = 20261102210000
WEBHOOK_PATH = "/v1/webhooks/razorpay"

DEFAULT_DSN = (
    "host=/tmp/savebite-pgtest17/sock port=54400 dbname=savebite_pgtest user=pgtest"
)
DEFAULT_POSTGREST_BIN = "/tmp/postgrest/postgrest"
POSTGREST_VERSION = "v12.2.3"
POSTGREST_DOWNLOAD_URL = (
    "https://github.com/PostgREST/postgrest/releases/download/v12.2.3/"
    "postgrest-v12.2.3-linux-static-x64.tar.xz"
)


def _require_psycopg():
    try:
        import psycopg
    except ImportError:
        pytest.fail(
            "psycopg is required for W9.1.3 tests (pip install psycopg[binary]); "
            "refusing to substitute a mock database client."
        )
    return psycopg


def _connect(psycopg, application_name: str):
    dsn = os.environ.get("SAVEBITE_PG_TEST_DSN", DEFAULT_DSN)
    return psycopg.connect(dsn, application_name=application_name)


def _dsn_to_postgrest_uri(dsn: str) -> str:
    """Convert a libpq DSN to a PostgREST db-uri.

    Handles the socket-dir form used by the disposable clusters
    (host=/path port=N dbname=X user=Y) and plain TCP forms.
    """
    if dsn.startswith("postgres://") or dsn.startswith("postgresql://"):
        return dsn
    parts = dict(p.split("=", 1) for p in dsn.split() if "=" in p)
    host, port = parts.get("host", "127.0.0.1"), parts.get("port", "5432")
    user, db = parts.get("user", "postgres"), parts.get("dbname", "postgres")
    return f"postgres://{user}@/{db}?host={host}&port={port}"


def _mint_jwt(secret: str, role: str = "service_role") -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    payload = b64(
        json.dumps({"role": role, "exp": 2000000000}, separators=(",", ":")).encode()
    )
    sig = b64(
        hmac.new(
            secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
    )
    return f"{header}.{payload}.{sig}"


# ---------------------------------------------------------------------------
# Scripted Razorpay provider (test-only substitute; labelled everywhere).
# ---------------------------------------------------------------------------


class FakeRazorpay:
    """Canned provider responses + a call log.

    get_payment / get_order return dicts shaped like the real Razorpay
    API. fail_get_payment_times injects a transient BadGatewayError (the
    same error the real client raises for an unavailable provider) so the
    retry test exercises the handler's real error path.
    """

    def __init__(self) -> None:
        self.payments: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail_get_payment_times = 0

    async def get_payment(self, payment_id: str) -> dict:
        self.calls.append(("get_payment", payment_id))
        if self.fail_get_payment_times > 0:
            self.fail_get_payment_times -= 1
            raise BadGatewayError("simulated transient provider failure")
        if payment_id not in self.payments:
            raise BadGatewayError("simulated provider 404")
        return self.payments[payment_id]

    async def get_order(self, order_id: str) -> dict:
        self.calls.append(("get_order", order_id))
        if order_id not in self.orders:
            raise BadGatewayError("simulated provider 404")
        return self.orders[order_id]

    async def create_order(self, *args, **kwargs) -> dict:  # not used here
        raise AssertionError("create_order must not be called by webhook tests")


def captured_entity(
    payment_id: str,
    gateway_order_id: str,
    amount_paise: int = 10000,
    currency: str = "INR",
    status: str = "captured",
) -> dict:
    return {
        "id": payment_id,
        "order_id": gateway_order_id,
        "status": status,
        "amount": amount_paise,
        "currency": currency,
    }


def webhook_body(event: str, entity: dict) -> bytes:
    return json.dumps(
        {"event": event, "payload": {"payment": {"entity": entity}}}
    ).encode()


def sign_body(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures: real PG 17 + real PostgREST + real FastAPI app.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg17_session(tmp_path_factory):
    psycopg = _require_psycopg()
    probe = _connect(psycopg, application_name="w913-probe")
    try:
        with probe.cursor() as cur:
            cur.execute("SHOW server_version")
            (version,) = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname = 'public' "
                "AND p.proname = 'backend_release_expired_reservations_v2'"
            )
            (nfunc,) = cur.fetchone()
        if not version.startswith("17."):
            pytest.fail(
                f"W9.1.3 requires PostgreSQL 17, but the test database reports "
                f"{version!r}. Point SAVEBITE_PG_TEST_DSN at a PG 17 cluster "
                f"(see module docstring) — refusing to test another version "
                f"while claiming 17."
            )
        if nfunc != 1:
            pytest.fail(
                "Test database is not bootstrapped: "
                "public.backend_release_expired_reservations_v2 not found. "
                "Run backend/tests/pg_bootstrap.py first (see module docstring)."
            )
        # TEST-ONLY deviation, disposable DB only (see module docstring):
        # the migration chain never grants USAGE ON SCHEMA private to
        # service_role, which makes every backend_* wrapper unusable via
        # PostgREST. Grant it here so the real PostgREST path can run and
        # the proposed fix is proven; production is untouched.
        with probe.cursor() as cur:
            cur.execute("GRANT USAGE ON SCHEMA private TO service_role")
            cur.execute(
                "SELECT has_schema_privilege('service_role', 'private', 'USAGE')"
            )
            (usage,) = cur.fetchone()
        probe.commit()
        assert usage is True, "test setup: USAGE grant did not take effect"
        install_barrier_objects(probe)
        probe.commit()
    finally:
        probe.close()
    yield {"psycopg": psycopg, "version": version}
    # The disposable database is dropped by pg_bootstrap.py --teardown;
    # this session deliberately leaves it standing for inspection.


class _RestV1ProxyHandler(BaseHTTPRequestHandler):
    """Strip Supabase's /rest/v1 prefix; forward everything else verbatim.

    Test-only emulation of the Kong routing in front of PostgREST on
    Supabase. The app, PostgREST, and PostgreSQL are all real; this only
    translates the URL layout (see module docstring).
    """

    protocol_version = "HTTP/1.1"

    def _forward(self) -> None:
        path = self.path
        if path.startswith("/rest/v1/"):
            path = path[len("/rest/v1") :]
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.postgrest_port, timeout=30
        )
        try:
            headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length", "connection")
            }
            conn.request(self.command, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for key, value in resp.getheaders():
                if key.lower() not in (
                    "connection",
                    "transfer-encoding",
                    "content-length",
                ):
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            conn.close()

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _forward

    def log_message(self, *args) -> None:
        pass


def _check_port_free(port: int, what: str) -> None:
    probe_sock = socket.socket()
    try:
        probe_sock.bind(("127.0.0.1", port))
    except OSError:
        pytest.fail(
            f"Port {port} is already in use — another {what} (possibly with "
            f"a different JWT secret) would silently answer these tests. Stop "
            f"it or set the corresponding SAVEBITE_*_PORT variable."
        )
    finally:
        probe_sock.close()


@pytest.fixture(scope="session")
def postgrest_session(pg17_session, tmp_path_factory):
    binary = os.environ.get("SAVEBITE_POSTGREST_BIN", DEFAULT_POSTGREST_BIN)
    if not os.path.isfile(binary):
        pytest.fail(
            f"PostgREST binary not found at {binary}. Download "
            f"{POSTGREST_VERSION} from {POSTGREST_DOWNLOAD_URL} (or set "
            f"SAVEBITE_POSTGREST_BIN). Refusing to substitute the transport."
        )
    port = int(os.environ.get("SAVEBITE_POSTGREST_PORT", "3001"))
    proxy_port = int(os.environ.get("SAVEBITE_POSTGREST_PROXY_PORT", "3002"))
    _check_port_free(port, "PostgREST")
    _check_port_free(proxy_port, "test reverse proxy")
    workdir = tmp_path_factory.mktemp("postgrest")
    jwt_secret = secrets.token_hex(32)
    dsn = os.environ.get("SAVEBITE_PG_TEST_DSN", DEFAULT_DSN)
    conf = (
        f'db-uri = "{_dsn_to_postgrest_uri(dsn)}"\n'
        'db-schemas = "public"\n'
        'db-anon-role = "anon"\n'
        f"server-port = {port}\n"
        f'jwt-secret = "{jwt_secret}"\n'
    )
    conf_path = workdir / "postgrest.conf"
    conf_path.write_text(conf)
    os.chmod(conf_path, 0o600)
    log_path = workdir / "server.log"
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [binary, str(conf_path)], stdout=log, stderr=subprocess.STDOUT
        )
    proxy = ThreadingHTTPServer(("127.0.0.1", proxy_port), _RestV1ProxyHandler)
    proxy.postgrest_port = port
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    base_url = f"http://127.0.0.1:{proxy_port}"
    try:
        opener = build_opener(ProxyHandler({}))  # never via an egress proxy

        def ready() -> bool:
            if proc.poll() is not None:
                pytest.fail(f"PostgREST exited early; see {log_path} for the cause.")
            try:
                with opener.open(base_url + "/rest/v1/", timeout=2) as resp:
                    return resp.status == 200
            except Exception:
                return False

        proxy_thread.start()
        wait_until("PostgREST ready", ready, timeout=30.0)
        yield {
            "base_url": base_url,
            "jwt": _mint_jwt(jwt_secret),
            "proc": proc,
            "log": log_path,
        }
    finally:
        proxy.shutdown()
        proxy.server_close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def db_conn(pg17_session):
    conn = _connect(pg17_session["psycopg"], application_name="w913-test")
    conn.autocommit = True  # every read sees the latest committed state
    try:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE {} RESTART IDENTITY CASCADE".format(
                    ", ".join(
                        list(TABLES_TRUNCATE) + ["private.payment_webhook_events"]
                    )
                )
            )
            cur.execute("DELETE FROM public.test_barrier_fired")
            cur.execute(
                "UPDATE public.test_ctl SET value = '0' WHERE key = 'barrier_enabled'"
            )
            cur.execute(
                "UPDATE public.test_ctl SET value = '' WHERE key = 'barrier_mode'"
            )
            cur.execute(
                "UPDATE public.test_ctl SET value = '0' WHERE key = 'fail_enabled'"
            )
            cur.execute(
                "UPDATE public.test_ctl SET value = '' WHERE key = 'fail_order_id'"
            )
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def observer(pg17_session):
    conn = _connect(pg17_session["psycopg"], application_name="w913-observer")
    conn.autocommit = True  # one transaction per poll (pg_stat_activity freshness)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def api_client(postgrest_session):
    """Real FastAPI app + real PostgREST service client + scripted provider.

    Returns (TestClient, FakeRazorpay, webhook_secret). The secret is
    generated per session and never printed.

    Sandbox quirk (see module docstring): the sandbox's proxy variables
    break httpx client construction, so they are removed for the duration
    of each test and restored afterwards. The app builds a fresh httpx
    client per RPC call, so the removal must be active during the test,
    not just at fixture setup.
    """
    proxy_vars = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    )
    saved = {k: os.environ.pop(k) for k in proxy_vars if k in os.environ}
    try:
        secret = secrets.token_hex(32)
        settings = Settings.model_construct(
            environment="development",
            supabase_url=postgrest_session["base_url"],
            supabase_publishable_key="w913-test-publishable",
            supabase_service_role_key=SecretStr(postgrest_session["jwt"]),
            razorpay_webhook_secret=SecretStr(secret),
            allowed_origins=[],
        )
        fake = FakeRazorpay()
        app = create_app(settings)
        app.dependency_overrides[get_service_client] = lambda: service_client(settings)
        app.dependency_overrides[get_razorpay_client] = lambda: fake
        client = TestClient(app, raise_server_exceptions=False)
        yield client, fake, secret
    finally:
        os.environ.update(saved)


# ---------------------------------------------------------------------------
# DB read helpers + thread helpers.
# ---------------------------------------------------------------------------


def count_webhook_events(conn, gateway_event_id: str | None = None) -> int:
    with conn.cursor() as cur:
        if gateway_event_id is None:
            cur.execute("SELECT count(*) FROM private.payment_webhook_events")
        else:
            cur.execute(
                "SELECT count(*) FROM private.payment_webhook_events "
                "WHERE gateway_event_id = %s",
                (gateway_event_id,),
            )
        (n,) = cur.fetchone()
    return n


def reservation_statuses(conn, order: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM public.inventory_reservations "
            "WHERE order_id = %s ORDER BY id",
            (order,),
        )
        return [r[0] for r in cur.fetchall()]


def _pid_by_app(observer, app_name: str) -> int | None:
    with observer.cursor() as cur:
        cur.execute(
            "SELECT pid FROM pg_stat_activity WHERE application_name = %s",
            (app_name,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def wait_for_waiter_on(observer, holder_pid: int, observer_pid: int) -> list[int]:
    """Wait until some session is queued on the holder's transaction."""
    holder_rows = locks_for(observer, holder_pid)
    holder_xids = {
        r["transactionid"]
        for r in holder_rows
        if r["locktype"] == "transactionid"
        and r["granted"]
        and r["transactionid"] is not None
    }
    assert holder_xids, f"holder {holder_pid} has no transactionid lock"

    def check():
        with observer.cursor() as cur:
            cur.execute(
                "SELECT pid FROM pg_locks WHERE locktype = 'transactionid' "
                "AND NOT granted AND mode = 'ShareLock' "
                "AND transactionid = ANY(%s)",
                (list(holder_xids),),
            )
            pids = [
                r[0] for r in cur.fetchall() if r[0] not in (holder_pid, observer_pid)
            ]
        return pids or None

    return wait_until("a session queued on the holder transaction", check)


class WebhookThread(threading.Thread):
    """POST a webhook in the background; the handler may block on a lock."""

    def __init__(self, client, body: bytes, headers: dict) -> None:
        super().__init__(daemon=True)
        self.client, self.body, self.headers = client, body, headers
        self.response = None
        self.error = None

    def run(self) -> None:
        try:
            self.response = self.client.post(
                WEBHOOK_PATH, content=self.body, headers=self.headers
            )
        except Exception as exc:  # captured for the test to assert on
            self.error = exc


class CleanupThread(threading.Thread):
    """Run the v2 cleanup RPC on its own connection (may pause at a barrier)."""

    def __init__(self, pg17_session, limit: int = 100) -> None:
        super().__init__(daemon=True)
        self.pg17_session, self.limit = pg17_session, limit
        self.result = None
        self.error = None

    def run(self) -> None:
        conn = _connect(self.pg17_session["psycopg"], application_name="w913-cleanup")
        try:
            self.result = call_cleanup(conn, self.limit)
        except Exception as exc:  # captured for the test to assert on
            self.error = exc
        finally:
            conn.close()


def post_webhook(client, fake, secret, event, entity, event_id):
    """Send one LOCALLY GENERATED HMAC-signed webhook request."""
    body = webhook_body(event, entity)
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": sign_body(secret, body),
        "X-Razorpay-Event-Id": event_id,
    }
    return client.post(WEBHOOK_PATH, content=body, headers=headers)


def configure_captured(
    fake: FakeRazorpay, tx: str, gateway_order_id: str, **pay_kwargs
):
    """Wire the scripted provider for a captured payment on one order."""
    payment_id = "pay_w913_" + uuid.uuid4().hex[:12]
    fake.payments[payment_id] = captured_entity(
        payment_id, gateway_order_id, **pay_kwargs
    )
    fake.orders[gateway_order_id] = {
        "id": gateway_order_id,
        "notes": {"savebite_payment_transaction_id": tx},
    }
    return payment_id


# ---------------------------------------------------------------------------
# Stage D — webhook security + reliability (real endpoint + real PG 17).
# Requests are LOCALLY GENERATED HMAC-signed requests, never provider
# deliveries. The provider side is the scripted FakeRazorpay (labelled).
# ---------------------------------------------------------------------------


def test_d1_valid_signature_captures(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    event_id = "evt_w913_d1_" + uuid.uuid4().hex[:12]

    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.captured",
        captured_entity(payment_id, gateway_order),
        event_id,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] is True

    # Provider fetch really happened (signature alone never confirms).
    assert ("get_payment", payment_id) in fake.calls
    assert ("get_order", gateway_order) in fake.calls
    assert count_webhook_events(db_conn, event_id) == 1
    assert fetch_order(db_conn, order) == ("confirmed", "captured")
    assert fetch_tx(db_conn, tx)[0] == "captured"
    assert reservation_statuses(db_conn, order) == ["consumed"]
    assert fetch_listing(db_conn, listing) == (100, 0, 2, 98)
    assert count_events(db_conn, order, "sold") == 1
    assert count_events(db_conn, order, "reservation_released") == 0
    assert count_order_events(db_conn, order, "confirmed") == 1
    assert_invariants(db_conn, [listing], [order])


def test_d2_invalid_signature_rejected_no_side_effect(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    body = webhook_body("payment.captured", captured_entity(payment_id, gateway_order))
    event_id = "evt_w913_d2_" + uuid.uuid4().hex[:12]

    resp = client.post(
        WEBHOOK_PATH,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "0" * 64,
            "X-Razorpay-Event-Id": event_id,
        },
    )
    assert resp.status_code == 401, resp.text
    assert count_webhook_events(db_conn, event_id) == 0
    assert fake.calls == [], "provider must not be consulted for a bad signature"
    assert fetch_order(db_conn, order) == ("pending_payment", "created")
    assert fetch_tx(db_conn, tx)[0] == "created"
    assert reservation_statuses(db_conn, order) == ["active"]
    assert fetch_listing(db_conn, listing) == (100, 2, 0, 98)
    assert_invariants(db_conn, [listing], [order])


def test_d3_modified_payload_after_signing_rejected(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    signed = webhook_body(
        "payment.captured", captured_entity(payment_id, gateway_order)
    )
    signature = sign_body(secret, signed)
    # Tamper AFTER signing: same shape, different amount.
    tampered = webhook_body(
        "payment.captured",
        captured_entity(payment_id, gateway_order, amount_paise=5000),
    )
    event_id = "evt_w913_d3_" + uuid.uuid4().hex[:12]

    resp = client.post(
        WEBHOOK_PATH,
        content=tampered,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": event_id,
        },
    )
    assert resp.status_code == 401, resp.text
    assert count_webhook_events(db_conn, event_id) == 0
    assert fake.calls == []
    assert fetch_order(db_conn, order) == ("pending_payment", "created")
    assert fetch_tx(db_conn, tx)[0] == "created"
    assert_invariants(db_conn, [listing], [order])


def test_d4_duplicate_delivery_exactly_once(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    event_id = "evt_w913_d4_" + uuid.uuid4().hex[:12]
    entity = captured_entity(payment_id, gateway_order)

    for _ in range(2):
        resp = post_webhook(client, fake, secret, "payment.captured", entity, event_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["processed"] is True

    assert count_webhook_events(db_conn, event_id) == 1
    assert fetch_order(db_conn, order) == ("confirmed", "captured")
    assert fetch_tx(db_conn, tx)[0] == "captured"
    assert count_events(db_conn, order, "sold") == 1
    assert count_order_events(db_conn, order, "confirmed") == 1
    assert fetch_listing(db_conn, listing) == (100, 0, 2, 98)
    assert_invariants(db_conn, [listing], [order])


def test_d5_out_of_order_failed_after_captured_no_regression(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    fake.orders[gateway_order] = {
        "id": gateway_order,
        "notes": {"savebite_payment_transaction_id": tx},
    }
    fake.payments[payment_id] = captured_entity(payment_id, gateway_order)

    # Failed event for a still-pending transaction: marks it failed.
    failed_event = "evt_w913_d5a_" + uuid.uuid4().hex[:12]
    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.failed",
        {"id": payment_id, "order_id": gateway_order},
        failed_event,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] is True
    assert fetch_tx(db_conn, tx)[0] == "failed"
    assert fetch_order(db_conn, order) == ("pending_payment", "failed")

    # Fresh order: capture first, then a delayed failed event must NOT
    # regress the capture.
    fx2 = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order2, tx2, listing2 = fx2["order"], fx2["tx"], fx2["listings"][0]
    gateway_order2 = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id2 = configure_captured(fake, tx2, gateway_order2)
    captured_event = "evt_w913_d5b_" + uuid.uuid4().hex[:12]
    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.captured",
        captured_entity(payment_id2, gateway_order2),
        captured_event,
    )
    assert resp.status_code == 200 and resp.json()["processed"] is True
    delayed_failed = "evt_w913_d5c_" + uuid.uuid4().hex[:12]
    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.failed",
        {"id": payment_id2, "order_id": gateway_order2},
        delayed_failed,
    )
    assert resp.status_code == 200, resp.text
    # The handler treats failed-after-captured as handled (HTTP 200, so
    # no retry storm) but reports processed=False with reason
    # already_captured — see the mark_failed except branch.
    assert resp.json()["processed"] is False
    assert resp.json()["reason"] == "already_captured"
    assert fetch_order(db_conn, order2) == ("confirmed", "captured")
    assert fetch_tx(db_conn, tx2)[0] == "captured"
    assert reservation_statuses(db_conn, order2) == ["consumed"]
    assert fetch_listing(db_conn, listing2) == (100, 0, 2, 98)
    assert_invariants(db_conn, [listing, listing2], [order, order2])


def test_d6_wrong_amount_reconciles_never_confirms(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    # Provider says ₹50 was captured; the order is ₹100.
    payment_id = configure_captured(fake, tx, gateway_order, amount_paise=5000)
    event_id = "evt_w913_d6_" + uuid.uuid4().hex[:12]

    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.captured",
        captured_entity(payment_id, gateway_order, amount_paise=5000),
        event_id,
    )
    # The handler returns processed=True for this path (confirm returned an
    # order id); the RECONCILIATION verdict lives in DB state, not the flag.
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] is True
    assert fetch_order(db_conn, order) == ("pending_payment", "reconciliation_required")
    assert fetch_tx(db_conn, tx) == ("reconciliation_required", "AMOUNT_MISMATCH")
    assert reservation_statuses(db_conn, order) == ["active"]
    assert fetch_listing(db_conn, listing) == (100, 2, 0, 98)
    assert count_events(db_conn, order, "sold") == 0
    assert count_order_events(db_conn, order, "confirmed") == 0
    assert_invariants(db_conn, [listing], [order])


def test_d7_wrong_currency_cannot_confirm(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order, currency="USD")
    event_id = "evt_w913_d7_" + uuid.uuid4().hex[:12]

    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.captured",
        captured_entity(payment_id, gateway_order, currency="USD"),
        event_id,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] is False
    assert count_webhook_events(db_conn, event_id) == 1  # recorded, not acted on
    assert fetch_order(db_conn, order) == ("pending_payment", "created")
    assert fetch_tx(db_conn, tx)[0] == "created"
    assert reservation_statuses(db_conn, order) == ["active"]
    assert_invariants(db_conn, [listing], [order])


def test_d8_gateway_order_mismatch_cannot_confirm(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    other_order = "order_w913_other_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    # Provider ties this payment to a DIFFERENT gateway order than the
    # webhook entity claims.
    fake.payments[payment_id] = captured_entity(payment_id, other_order)
    event_id = "evt_w913_d8_" + uuid.uuid4().hex[:12]

    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.captured",
        captured_entity(payment_id, gateway_order),
        event_id,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] is False
    assert fetch_order(db_conn, order) == ("pending_payment", "created")
    assert fetch_tx(db_conn, tx)[0] == "created"
    assert reservation_statuses(db_conn, order) == ["active"]
    assert_invariants(db_conn, [listing], [order])


def test_d9_provider_verification_signature_alone_never_confirms(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    # Payload CLAIMS captured, but the provider says the payment is still
    # merely created (not captured). A valid signature must not confirm.
    fake.payments[payment_id] = captured_entity(
        payment_id, gateway_order, status="created"
    )
    event_id = "evt_w913_d9_" + uuid.uuid4().hex[:12]

    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.captured",
        captured_entity(payment_id, gateway_order),
        event_id,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] is False
    assert ("get_payment", payment_id) in fake.calls, (
        "handler must fetch provider payment details before confirming"
    )
    assert fetch_order(db_conn, order) == ("pending_payment", "created")
    assert fetch_tx(db_conn, tx)[0] == "created"
    assert reservation_statuses(db_conn, order) == ["active"]
    assert_invariants(db_conn, [listing], [order])


def test_d10_retry_after_transient_provider_failure(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    fake.fail_get_payment_times = 1  # first provider fetch fails transiently
    event_id = "evt_w913_d10_" + uuid.uuid4().hex[:12]
    entity = captured_entity(payment_id, gateway_order)

    first = post_webhook(client, fake, secret, "payment.captured", entity, event_id)
    assert first.status_code == 200, first.text
    assert first.json()["processed"] is False
    assert fetch_order(db_conn, order) == ("pending_payment", "created")
    assert fetch_tx(db_conn, tx)[0] == "created"
    # The event was recorded (record-before-act) even though processing failed.
    assert count_webhook_events(db_conn, event_id) == 1

    second = post_webhook(client, fake, secret, "payment.captured", entity, event_id)
    assert second.status_code == 200, second.text
    assert second.json()["processed"] is True
    assert count_webhook_events(db_conn, event_id) == 1
    assert fetch_order(db_conn, order) == ("confirmed", "captured")
    assert fetch_tx(db_conn, tx)[0] == "captured"
    assert count_events(db_conn, order, "sold") == 1
    assert count_order_events(db_conn, order, "confirmed") == 1
    assert fetch_listing(db_conn, listing) == (100, 0, 2, 98)
    assert_invariants(db_conn, [listing], [order])


# ---------------------------------------------------------------------------
# Stage E — payment + reservation races (real webhook handler + real PG 17).
# Cleanup runs through the same v2 RPC the worker calls; the payment side
# always goes through the real HTTP webhook handler. Webhook requests are
# LOCALLY GENERATED HMAC-signed requests (see module docstring).
# ---------------------------------------------------------------------------


def _lock_holder(pg17_session):
    conn = _connect(pg17_session["psycopg"], application_name="w913-driver")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (BARRIER_KEY,))
    return conn


def _release_holder(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (BARRIER_KEY,))
    conn.close()


def _advisory_waiters(observer, exclude_pids: list[int]) -> list[int]:
    """Sessions currently blocked on a lock (the barrier pause)."""
    with observer.cursor() as cur:
        cur.execute(
            "SELECT pid FROM pg_stat_activity WHERE state = 'active' "
            "AND wait_event_type = 'Lock' AND pid <> ALL(%s)",
            (exclude_pids,),
        )
        return [r[0] for r in cur.fetchall()]


def test_e_a_cleanup_wins_then_captured_reconciles(
    pg17_session, db_conn, observer, api_client
):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=True, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    event_id = "evt_w913_ea_" + uuid.uuid4().hex[:12]
    body = webhook_body("payment.captured", captured_entity(payment_id, gateway_order))
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": sign_body(secret, body),
        "X-Razorpay-Event-Id": event_id,
    }

    holder = _lock_holder(pg17_session)
    try:
        set_barrier(db_conn, "expire")
        cleanup = CleanupThread(pg17_session)
        cleanup.start()
        # Pause detection must use pg_stat_activity, NOT the
        # test_barrier_fired row: that INSERT is part of the paused
        # transaction itself, so it stays invisible to observers until
        # the transaction commits. (This exact mistake cost one full
        # run: the count never becomes visible while paused.)
        cleanup_pid = wait_until(
            "cleanup session registered",
            lambda: _pid_by_app(observer, "w913-cleanup"),
        )
        wait_blocked(observer, cleanup_pid, "cleanup paused at barrier")
        # The captured webhook arrives while cleanup owns the order lock.
        webhook = WebhookThread(client, body, headers)
        webhook.start()
        observer_pid = backend_pid(observer)
        wait_for_waiter_on(observer, cleanup_pid, observer_pid)
        _release_holder(holder)
        holder = None
        cleanup.join(timeout=30)
        assert not cleanup.is_alive(), "cleanup thread did not finish"
        assert cleanup.error is None, f"cleanup raised: {cleanup.error!r}"
        assert cleanup.result["released"] == 1, cleanup.result
        webhook.join(timeout=30)
        assert not webhook.is_alive(), "webhook thread did not finish"
        assert webhook.error is None, f"webhook raised: {webhook.error!r}"
        assert webhook.response.status_code == 200, webhook.response.text
        assert webhook.response.json()["processed"] is True
    finally:
        if holder is not None:
            _release_holder(holder)
        from tests.test_pg_concurrency import clear_barrier

        clear_barrier(db_conn)

    # Cleanup won: order expired, payment reconciled, never confirmed,
    # released stock never sold or consumed twice.
    assert fetch_order(db_conn, order) == ("expired", "reconciliation_required")
    assert fetch_tx(db_conn, tx) == (
        "reconciliation_required",
        "RESERVATION_NOT_ACTIVE_OR_INCOMPLETE",
    )
    assert reservation_statuses(db_conn, order) == ["expired"]
    assert fetch_listing(db_conn, listing) == (100, 0, 0, 100)
    assert count_events(db_conn, order, "reservation_released") == 1
    assert count_events(db_conn, order, "sold") == 0
    assert count_order_events(db_conn, order, "expired") == 1
    assert count_order_events(db_conn, order, "confirmed") == 0
    assert count_webhook_events(db_conn, event_id) == 1
    assert_invariants(db_conn, [listing], [order])


def test_e_b_confirmation_wins_cleanup_does_not_block(
    pg17_session, db_conn, observer, api_client
):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    event_id = "evt_w913_eb_" + uuid.uuid4().hex[:12]
    body = webhook_body("payment.captured", captured_entity(payment_id, gateway_order))
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": sign_body(secret, body),
        "X-Razorpay-Event-Id": event_id,
    }

    holder = _lock_holder(pg17_session)
    try:
        set_barrier(db_conn, "consume")
        webhook = WebhookThread(client, body, headers)
        webhook.start()
        observer_pid = backend_pid(observer)
        # The paused confirm holds the order lock; detect the pause via
        # pg_stat_activity (see the E_A comment: the barrier-fired row
        # is invisible while the pausing transaction is uncommitted).
        # The confirm runs on a PostgREST pooled backend, so it is found
        # as "some Lock-waiting session", not by application name.
        wait_until(
            "confirm session blocked on the barrier lock",
            lambda: _advisory_waiters(observer, [observer_pid]) or None,
        )
        # Cleanup must return promptly with zero work, not block behind it.
        cleanup = CleanupThread(pg17_session)
        cleanup.start()
        cleanup.join(timeout=20)
        assert not cleanup.is_alive(), "cleanup blocked instead of skipping"
        assert cleanup.error is None, f"cleanup raised: {cleanup.error!r}"
        assert cleanup.result["released"] == 0, cleanup.result
        _release_holder(holder)
        holder = None
        webhook.join(timeout=30)
        assert not webhook.is_alive(), "webhook thread did not finish"
        assert webhook.error is None, f"webhook raised: {webhook.error!r}"
        assert webhook.response.status_code == 200, webhook.response.text
        assert webhook.response.json()["processed"] is True
    finally:
        if holder is not None:
            _release_holder(holder)
        from tests.test_pg_concurrency import clear_barrier

        clear_barrier(db_conn)

    # Confirmation won: exactly-once consumption; later cleanup untouched.
    assert fetch_order(db_conn, order) == ("confirmed", "captured")
    assert fetch_tx(db_conn, tx)[0] == "captured"
    assert reservation_statuses(db_conn, order) == ["consumed"]
    assert fetch_listing(db_conn, listing) == (100, 0, 2, 98)
    assert count_events(db_conn, order, "sold") == 1
    assert count_events(db_conn, order, "reservation_released") == 0
    assert count_order_events(db_conn, order, "confirmed") == 1
    assert call_cleanup(db_conn)["released"] == 0
    assert count_events(db_conn, order, "reservation_released") == 0
    assert_invariants(db_conn, [listing], [order])


def test_e_c_late_captured_payment_reconciles(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=True, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    event_id = "evt_w913_ec_" + uuid.uuid4().hex[:12]

    # Expire + release first. The v2 cleanup marks an expired, never-paid
    # order (status expired, payment_status failed) — see the RELEASE+EXPIRE
    # tier in 20261102210000_w911_cleanup_lock_order.sql.
    assert call_cleanup(db_conn)["released"] == 1
    assert fetch_order(db_conn, order) == ("expired", "failed")
    assert fetch_listing(db_conn, listing) == (100, 0, 0, 100)

    # Then the captured notification arrives late.
    resp = post_webhook(
        client,
        fake,
        secret,
        "payment.captured",
        captured_entity(payment_id, gateway_order),
        event_id,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] is True
    assert fetch_order(db_conn, order) == ("expired", "reconciliation_required")
    assert fetch_tx(db_conn, tx) == (
        "reconciliation_required",
        "RESERVATION_NOT_ACTIVE_OR_INCOMPLETE",
    )
    assert reservation_statuses(db_conn, order) == ["expired"]
    assert fetch_listing(db_conn, listing) == (100, 0, 0, 100)
    assert count_events(db_conn, order, "sold") == 0
    assert count_order_events(db_conn, order, "confirmed") == 0
    assert count_webhook_events(db_conn, event_id) == 1
    assert_invariants(db_conn, [listing], [order])


def test_e_d_duplicate_captured_webhook_three_times(db_conn, api_client):
    client, fake, secret = api_client
    fx = make_fixture(db_conn, n_items=1, qty=2, expired=False, tx_status="created")
    order, tx, listing = fx["order"], fx["tx"], fx["listings"][0]
    gateway_order = "order_w913_" + uuid.uuid4().hex[:12]
    payment_id = configure_captured(fake, tx, gateway_order)
    event_id = "evt_w913_ed_" + uuid.uuid4().hex[:12]
    entity = captured_entity(payment_id, gateway_order)

    for _ in range(3):
        resp = post_webhook(client, fake, secret, "payment.captured", entity, event_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["processed"] is True

    assert count_webhook_events(db_conn, event_id) == 1
    assert fetch_order(db_conn, order) == ("confirmed", "captured")
    assert fetch_tx(db_conn, tx)[0] == "captured"
    assert reservation_statuses(db_conn, order) == ["consumed"]
    assert fetch_listing(db_conn, listing) == (100, 0, 2, 98)
    assert count_events(db_conn, order, "sold") == 1
    assert count_order_events(db_conn, order, "confirmed") == 1
    assert_invariants(db_conn, [listing], [order])
