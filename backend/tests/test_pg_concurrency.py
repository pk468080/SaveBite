"""SaveBite W9.1.2 — real PostgreSQL concurrency tests.

These tests run against a REAL PostgreSQL database. They are not unit
tests, not mocks, and not SQL parsing: every assertion below reads
back database state after genuinely concurrent sessions, and the
lock-order tests observe real ``pg_locks`` / ``pg_stat_activity``
rows while two sessions contend.

Requirements:

- A bootstrapped disposable database (see ``pg_bootstrap.py``).
  Start one first::

      python3 backend/tests/pg_bootstrap.py \
          --pgdata /tmp/savebite-pgtest/data \
          --socket-dir /tmp/savebite-pgtest/sock --port 54399

- ``psycopg`` (v3) installed for the test run::

      pip install "psycopg[binary]"

- The database DSN, via ``SAVEBITE_PG_TEST_DSN`` (default:
  ``host=/tmp/savebite-pgtest/sock port=54399 dbname=savebite_pgtest
  user=pgtest``).

FAIL-CLEARLY RULE (do not weaken it): if psycopg is missing, if the
database is unreachable, or if the database was not bootstrapped with
the W9.1/W9.1.1 functions, the session fixture fails loudly. These
tests never substitute a mock, a fake, or SQLite, and a run without
PostgreSQL must never report a pass. To run the rest of the backend
suite without PostgreSQL, exclude this file explicitly
(``pytest --ignore=backend/tests/test_pg_concurrency.py``) — that is
a deliberate exclusion, not a pass.

Deterministic coordination: lock-contention tests pause a session
mid-function with a test-only trigger (installed in the disposable
database only, never in a migration) that waits on an advisory lock
held by the test driver, while the driver observes the waiting
backend in ``pg_stat_activity`` / ``pg_locks``. No test depends on
``sleep`` timing to create a race; sleeps appear only as poll
intervals while waiting for an observed condition, with a timeout
that fails the test instead of passing silently.

What is tested (W9.1.2 Stage D):

- Test 1: cleanup holds the order lock first; confirmation must
  reconcile, never falsely confirm.
- Test 2: confirmation holds the order lock first; cleanup must skip
  via SKIP LOCKED, never deadlock.
- Test 3: two cleanup workers on one order, repeated.
- Test 4: duplicate cleanup, rollback atomicity, induced-failure retry.
- Test 5: bounded batch behaviour, including invalid limits.
- Test 6: every W9.1 payment-status tier.
- Test 7: residual listing-lock contention (two cleanups, opposite
  listing order) — deadlock atomicity and retry safety.

Invariants are asserted from database state after every scenario
(see ``assert_invariants``), not from returned JSON alone.
"""

from __future__ import annotations

import threading
import time
import uuid
from decimal import Decimal

import pytest

DEFAULT_DSN = (
    "host=/tmp/savebite-pgtest/sock port=54399 dbname=savebite_pgtest user=pgtest"
)
BARRIER_KEY = 20261102210000
TABLES_TRUNCATE = (
    "auth.users",
    "public.merchants",
    "public.stores",
    "public.listings",
    "public.orders",
    "public.order_items",
    "public.inventory_reservations",
    "public.inventory_events",
    "public.order_status_events",
    "private.payment_transactions",
)


def _import_psycopg():
    try:
        import psycopg
        from psycopg import errors as pg_errors
    except ImportError as exc:  # pragma: no cover - environment failure
        pytest.fail(
            "PostgreSQL concurrency tests require psycopg: "
            f"pip install 'psycopg[binary]' (original error: {exc})"
        )
    return psycopg, pg_errors


def _dsn() -> str:
    import os

    return os.environ.get("SAVEBITE_PG_TEST_DSN", DEFAULT_DSN)


def _connect(psycopg, **kwargs):
    conn = psycopg.connect(_dsn(), **kwargs)
    conn.autocommit = False
    return conn


# ---------------------------------------------------------------------------
# Session setup: database must exist and be bootstrapped, or fail loudly.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_session():
    psycopg, pg_errors = _import_psycopg()
    try:
        probe = _connect(psycopg, application_name="w912-probe")
    except Exception as exc:
        pytest.fail(
            f"PostgreSQL test database unreachable (DSN={_dsn()}). Start one with "
            f"backend/tests/pg_bootstrap.py first. Original error: {exc}"
        )
    try:
        with probe.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname = 'private' "
                "AND p.proname = 'release_expired_reservations_v2'"
            )
            (count,) = cur.fetchone()
        if count != 1:
            pytest.fail(
                "PostgreSQL test database is not bootstrapped: "
                "private.release_expired_reservations_v2 not found. Run "
                "backend/tests/pg_bootstrap.py first."
            )
        install_barrier_objects(probe)
        probe.commit()
    finally:
        probe.close()
    yield psycopg, pg_errors
    # The disposable database is dropped by pg_bootstrap.py --teardown;
    # this session deliberately leaves it standing for inspection.


@pytest.fixture()
def conn(pg_session):
    psycopg, _ = pg_session
    c = _connect(psycopg, application_name="w912-test")
    try:
        with c.cursor() as cur:
            cur.execute(
                "TRUNCATE {} RESTART IDENTITY CASCADE".format(
                    ", ".join(TABLES_TRUNCATE)
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
        c.commit()
        yield c
    finally:
        try:
            c.rollback()
        except Exception:
            pass
        c.close()


# ---------------------------------------------------------------------------
# Test-only barrier objects (disposable database only, never a migration).
# ---------------------------------------------------------------------------

BARRIER_SQL = """
CREATE TABLE IF NOT EXISTS public.test_ctl (
    key text PRIMARY KEY, value text NOT NULL DEFAULT ''
);
DROP TABLE IF EXISTS public.test_barrier_fired;
CREATE TABLE public.test_barrier_fired (
    txid xid8 PRIMARY KEY
);
CREATE OR REPLACE FUNCTION public.test_pause()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $func$
declare
  v_enabled text;
  v_mode text;
begin
  SELECT value INTO v_enabled FROM public.test_ctl WHERE key = 'barrier_enabled';
  IF v_enabled IS DISTINCT FROM '1' THEN RETURN NEW; END IF;
  SELECT value INTO v_mode FROM public.test_ctl WHERE key = 'barrier_mode';
  IF TG_ARGV[0] = 'reservation' THEN
    IF v_mode = 'listing' THEN
      RETURN NEW;
    END IF;
    IF (v_mode = 'expire' AND NEW.status <> 'expired')
       OR (v_mode = 'consume' AND NEW.status <> 'consumed') THEN
      RETURN NEW;
    END IF;
  ELSIF TG_ARGV[0] = 'listing' THEN
    IF v_mode <> 'listing' THEN RETURN NEW; END IF;
  ELSE
    RETURN NEW;
  END IF;
  IF EXISTS (SELECT 1 FROM public.test_barrier_fired
             WHERE txid = pg_catalog.pg_current_xact_id()) THEN
    RETURN NEW;
  END IF;
  INSERT INTO public.test_barrier_fired VALUES (pg_catalog.pg_current_xact_id());
  PERFORM pg_catalog.pg_advisory_xact_lock(20261102210000);
  RETURN NEW;
end;
$func$;
DROP TRIGGER IF EXISTS trg_test_pause_reservation ON public.inventory_reservations;
CREATE TRIGGER trg_test_pause_reservation
  BEFORE UPDATE OF status ON public.inventory_reservations
  FOR EACH ROW EXECUTE FUNCTION public.test_pause('reservation');
DROP TRIGGER IF EXISTS trg_test_pause_listing ON public.listings;
CREATE TRIGGER trg_test_pause_listing
  BEFORE UPDATE ON public.listings
  FOR EACH ROW EXECUTE FUNCTION public.test_pause('listing');
CREATE OR REPLACE FUNCTION public.test_fail_second_release()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $func$
declare
  v_enabled text;
  v_order text;
begin
  SELECT value INTO v_enabled FROM public.test_ctl WHERE key = 'fail_enabled';
  IF v_enabled IS DISTINCT FROM '1' THEN RETURN NEW; END IF;
  SELECT value INTO v_order FROM public.test_ctl WHERE key = 'fail_order_id';
  IF NEW.order_id IS NOT NULL AND NEW.order_id::text = v_order
     AND NEW.event_type = 'reservation_released'
     AND (SELECT count(*) FROM public.inventory_events
          WHERE order_id = NEW.order_id
            AND event_type = 'reservation_released') >= 1 THEN
    RAISE EXCEPTION 'test-induced failure on second release' USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
end;
$func$;
DROP TRIGGER IF EXISTS trg_test_fail_second_release ON public.inventory_events;
CREATE TRIGGER trg_test_fail_second_release
  BEFORE INSERT ON public.inventory_events
  FOR EACH ROW EXECUTE FUNCTION public.test_fail_second_release();
INSERT INTO public.test_ctl (key, value) VALUES
  ('barrier_enabled', '0'), ('barrier_mode', ''),
  ('fail_enabled', '0'), ('fail_order_id', '')
ON CONFLICT (key) DO NOTHING;
"""


def install_barrier_objects(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(BARRIER_SQL)


def set_barrier(conn, mode: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE public.test_ctl SET value = '1' WHERE key = 'barrier_enabled'"
        )
        cur.execute(
            "UPDATE public.test_ctl SET value = %s WHERE key = 'barrier_mode'", (mode,)
        )
    conn.commit()


def clear_barrier(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE public.test_ctl SET value = '0' WHERE key = 'barrier_enabled'"
        )
        cur.execute("UPDATE public.test_ctl SET value = '' WHERE key = 'barrier_mode'")
        cur.execute("DELETE FROM public.test_barrier_fired")
    conn.commit()


# ---------------------------------------------------------------------------
# Observation helpers (pg_stat_activity / pg_locks, poll-until with timeout).
# ---------------------------------------------------------------------------


def backend_pid(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_backend_pid()")
        (pid,) = cur.fetchone()
    return pid


def activity(observer, pid: int) -> dict | None:
    with observer.cursor() as cur:
        cur.execute(
            "SELECT state, wait_event_type, wait_event, query FROM pg_stat_activity "
            "WHERE pid = %s",
            (pid,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "state": row[0],
        "wait_event_type": row[1],
        "wait_event": row[2],
        "query": row[3],
    }


def locks_for(observer, pid: int) -> list[dict]:
    with observer.cursor() as cur:
        cur.execute(
            "SELECT l.locktype, l.mode, l.granted, c.relname, l.transactionid "
            "FROM pg_locks l LEFT JOIN pg_class c ON c.oid = l.relation "
            "WHERE l.pid = %s",
            (pid,),
        )
        return [
            {
                "locktype": r[0],
                "mode": r[1],
                "granted": r[2],
                "relname": r[3],
                "transactionid": r[4],
            }
            for r in cur.fetchall()
        ]


def wait_until(desc: str, fn, timeout: float = 20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(0.05)
    pytest.fail(f"timed out waiting for: {desc} (last observation: {last!r})")


def wait_blocked(observer, pid: int, desc: str):
    return wait_until(
        f"{desc} (backend {pid} blocked on a lock)",
        lambda: (lambda a: a and a["wait_event_type"] == "Lock")(
            activity(observer, pid)
        ),
    )


def wait_for_transaction(observer, waiter_pid: int, holder_pid: int, desc: str):
    """Wait until the waiter is queued on the holder's transaction.

    A session waiting on a FOR UPDATE row lock shows up in pg_locks as
    an ungranted transactionid ShareLock on the holder's xid (not as an
    ungranted tuple lock), so the precise check is: waiter's ungranted
    ShareLock transactionid == holder's granted ExclusiveLock xid.
    Combined with the holder holding the orders RowShareLock, this
    proves the waiter is queued behind the holder's order lock.
    """
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
        rows = locks_for(observer, waiter_pid)
        return any(
            r["locktype"] == "transactionid"
            and not r["granted"]
            and r["mode"] == "ShareLock"
            and r["transactionid"] in holder_xids
            for r in rows
        )

    return wait_until(desc, check)


class SessionThread(threading.Thread):
    """Run one session's work on its own connection; capture result/error."""

    def __init__(self, pg_session, fn, app_name: str):
        super().__init__(daemon=True)
        self.pg_session = pg_session
        self.fn = fn
        self.app_name = app_name
        self.result = None
        self.error = None

    def run(self) -> None:
        psycopg, _ = self.pg_session
        conn = _connect(psycopg, application_name=self.app_name)
        try:
            self.result = self.fn(conn)
        except Exception as exc:  # captured for the test to assert on
            self.error = exc
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()


# ---------------------------------------------------------------------------
# Fixture builders (direct SQL inserts; auth-dependent functions are not
# executed, so no auth.uid() context is needed).
# ---------------------------------------------------------------------------


def uid() -> str:
    return str(uuid.uuid4())


def make_fixture(
    conn,
    *,
    n_items: int = 1,
    qty: int = 2,
    expired: bool = True,
    tx_status: str | None = "created",
    order_payment_status: str = "created",
    listing_total: int = 100,
    expiry_offsets_min: list[int] | None = None,
    shared_listings: list[str] | None = None,
):
    """Build merchant/store/listing(s)/order/items/reservations (+ tx).

    Returns a dict of ids and rows. Reservations are 'active'; expired
    ones get expires_at in the past, live ones in the future. Each item
    gets exactly one reservation (unique partial index). When
    shared_listings is given, items map onto those listings in order
    (used by the listing-contention test); otherwise one fresh listing
    per item is created.
    """
    customer = uid()
    merchant = uid()
    store = uid()
    past = "now() - interval '10 minutes'"
    future = "now() + interval '10 minutes'"
    with conn.cursor() as cur:
        cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (customer,))
        cur.execute(
            "INSERT INTO public.merchants (id, legal_name, display_name, "
            "business_type, created_by) VALUES (%s, 'Test Merchant', 'Test', "
            "'restaurant', %s)",
            (merchant, customer),
        )
        cur.execute(
            "INSERT INTO public.stores (id, merchant_id, name, slug, "
            "address_line_1, city, state, pincode) VALUES "
            "(%s, %s, 'Test Store', %s, '1 Test Road', 'Test City', "
            "'Test State', '110001')",
            (store, merchant, "store-" + uuid.uuid4().hex[:12]),
        )
        listing_ids: list[str] = []
        if shared_listings:
            listing_ids = list(shared_listings)
        else:
            for _ in range(n_items):
                lid = uid()
                cur.execute(
                    "INSERT INTO public.listings (id, store_id, listing_type, "
                    "title, reference_value, selling_price, total_quantity, "
                    "reserved_quantity, sold_quantity, sale_starts_at, "
                    "sale_ends_at, pickup_starts_at, pickup_ends_at, "
                    "created_by) VALUES (%s, %s, 'surprise_bag', 'Bag', 100, "
                    "50, %s, 0, 0, now() - interval '1 hour', "
                    "now() + interval '2 hours', now(), "
                    "now() + interval '3 hours', %s)",
                    (lid, store, listing_total, customer),
                )
                listing_ids.append(lid)
        order = uid()
        cur.execute(
            "INSERT INTO public.orders (id, order_number, customer_id, "
            "merchant_id, store_id, status, payment_status, subtotal_amount, "
            "total_amount, pickup_starts_at, pickup_ends_at, "
            "request_idempotency_key, request_hash) VALUES (%s, %s, %s, %s, "
            "%s, 'pending_payment', %s, 100, 100, now(), "
            "now() + interval '1 hour', %s, 'hash')",
            (
                order,
                "ORD-" + uuid.uuid4().hex[:12],
                customer,
                merchant,
                store,
                order_payment_status,
                "key-" + uuid.uuid4().hex,
            ),
        )
        item_ids, reservation_ids = [], []
        for i in range(n_items):
            item = uid()
            res = uid()
            lid = listing_ids[i % len(listing_ids)]
            cur.execute(
                "INSERT INTO public.order_items (id, order_id, listing_id, "
                "listing_type, listing_title_snapshot, quantity, unit_price, "
                "reference_value_snapshot, line_total) VALUES (%s, %s, %s, "
                "'surprise_bag', 'Bag', %s, 50, 100, 100)",
                (item, order, lid, qty),
            )
            if expiry_offsets_min is not None:
                off = expiry_offsets_min[i]
                exp = (
                    f"now() + interval '{off} minutes'"
                    if off >= 0
                    else f"now() - interval '{-off} minutes'"
                )
            else:
                exp = past if expired else future
            cur.execute(
                "INSERT INTO public.inventory_reservations (id, order_id, "
                "order_item_id, listing_id, quantity, status, expires_at) "
                "VALUES ({}, {}, {}, {}, {}, 'active', {})".format(
                    "%s", "%s", "%s", "%s", "%s", exp
                ),
                (res, order, item, lid, qty),
            )
            cur.execute(
                "UPDATE public.listings SET reserved_quantity = "
                "reserved_quantity + %s WHERE id = %s",
                (qty, lid),
            )
            item_ids.append(item)
            reservation_ids.append(res)
        tx = None
        if tx_status is not None:
            tx = uid()
            cur.execute(
                "INSERT INTO private.payment_transactions (id, order_id, "
                "gateway, amount, status, idempotency_key) VALUES "
                "(%s, %s, 'razorpay', 100, %s, %s)",
                (tx, order, tx_status, "txkey-" + uuid.uuid4().hex),
            )
    conn.commit()
    return {
        "customer": customer,
        "merchant": merchant,
        "store": store,
        "listings": listing_ids,
        "order": order,
        "items": item_ids,
        "reservations": reservation_ids,
        "tx": tx,
    }


def call_cleanup(conn, limit: int = 100):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT public.backend_release_expired_reservations_v2(%s)", (limit,)
        )
        (result,) = cur.fetchone()
    conn.commit()
    return result


def call_confirm(conn, tx: str, gateway_payment_id: str, amount=Decimal("100")):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT public.backend_confirm_payment_capture(%s, %s, %s, true)",
            (tx, gateway_payment_id, amount),
        )
        (result,) = cur.fetchone()
    conn.commit()
    return result


def fetch_order(conn, order: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, payment_status FROM public.orders WHERE id = %s", (order,)
        )
        return cur.fetchone()


def fetch_tx(conn, tx: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, failure_code FROM private.payment_transactions WHERE id = %s",
            (tx,),
        )
        return cur.fetchone()


def fetch_listing(conn, listing: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT total_quantity, reserved_quantity, sold_quantity, "
            "available_quantity FROM public.listings WHERE id = %s",
            (listing,),
        )
        return cur.fetchone()


def count_events(conn, order: str, event_type: str, reason: str | None = None):
    with conn.cursor() as cur:
        if reason is None:
            cur.execute(
                "SELECT count(*) FROM public.inventory_events WHERE order_id = %s "
                "AND event_type = %s",
                (order, event_type),
            )
        else:
            cur.execute(
                "SELECT count(*) FROM public.inventory_events WHERE order_id = %s "
                "AND event_type = %s AND reason = %s",
                (order, event_type, reason),
            )
        (n,) = cur.fetchone()
    return n


def count_order_events(conn, order: str, to_status: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM public.order_status_events WHERE order_id = %s "
            "AND to_status = %s",
            (order, to_status),
        )
        (n,) = cur.fetchone()
    return n


def assert_invariants(conn, listing_ids: list[str], order_ids: list[str]) -> None:
    """Database-state invariants, checked after every scenario."""
    with conn.cursor() as cur:
        for lid in listing_ids:
            cur.execute(
                "SELECT reserved_quantity, sold_quantity, total_quantity, "
                "available_quantity FROM public.listings WHERE id = %s",
                (lid,),
            )
            reserved, sold, total, available = cur.fetchone()
            assert reserved >= 0, f"reserved_quantity negative for {lid}"
            assert sold >= 0, f"sold_quantity negative for {lid}"
            assert available == total - reserved - sold, f"available mismatch {lid}"
            cur.execute(
                "SELECT coalesce(sum(quantity), 0) FROM public.inventory_reservations "
                "WHERE listing_id = %s AND status = 'active'",
                (lid,),
            )
            (active_sum,) = cur.fetchone()
            assert reserved == active_sum, (
                f"reserved {reserved} != active reservation sum {active_sum} for {lid}"
            )
            cur.execute(
                "SELECT coalesce(sum(quantity), 0) FROM public.inventory_reservations "
                "WHERE listing_id = %s AND status = 'consumed'",
                (lid,),
            )
            (consumed_sum,) = cur.fetchone()
            assert sold == consumed_sum, (
                f"sold {sold} != consumed sum {consumed_sum} for {lid}"
            )
            cur.execute(
                "SELECT reservation_id, count(*) FROM public.inventory_events "
                "WHERE listing_id = %s AND event_type = 'reservation_released' "
                "GROUP BY reservation_id HAVING count(*) > 1",
                (lid,),
            )
            dupes = cur.fetchall()
            assert not dupes, f"duplicate release events: {dupes!r}"
            cur.execute(
                "SELECT reservation_id, count(*) FROM public.inventory_events "
                "WHERE listing_id = %s AND event_type = 'sold' "
                "GROUP BY reservation_id HAVING count(*) > 1",
                (lid,),
            )
            dupes = cur.fetchall()
            assert not dupes, f"duplicate sold events: {dupes!r}"
        for oid in order_ids:
            cur.execute(
                "SELECT count(*) FROM public.order_status_events WHERE order_id = %s "
                "AND to_status = 'expired'",
                (oid,),
            )
            (expiry_events,) = cur.fetchone()
            assert expiry_events <= 1, f"duplicate expiry events for {oid}"
            cur.execute(
                "SELECT status, payment_status FROM public.orders WHERE id = %s", (oid,)
            )
            status, payment_status = cur.fetchone()
            assert not (status == "expired" and payment_status == "captured"), (
                f"expired order with captured payment: {oid}"
            )
            if status == "confirmed":
                assert payment_status == "captured", (
                    f"confirmed order without captured payment: {oid}"
                )


# ---------------------------------------------------------------------------
# Stage C checks: functions, signatures, wrapper resolution, grants.
# ---------------------------------------------------------------------------


def test_00_functions_signatures_and_grants(pg_session, conn):
    psycopg, _ = pg_session
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_get_function_arguments(p.oid) FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'private' AND p.proname = 'release_expired_reservations_v2'"
        )
        assert cur.fetchone()[0] == "p_limit integer DEFAULT 100"
        cur.execute(
            "SELECT pg_get_function_arguments(p.oid) FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = 'backend_release_expired_reservations_v2'"
        )
        assert cur.fetchone()[0] == "p_limit integer DEFAULT 100"
        cur.execute(
            "SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = 'backend_release_expired_reservations_v2'"
        )
        assert "private.release_expired_reservations_v2" in cur.fetchone()[0]
        for role, want in (
            ("anon", False),
            ("authenticated", False),
            ("service_role", True),
        ):
            cur.execute(
                "SELECT has_function_privilege(%s, "
                "'public.backend_release_expired_reservations_v2(integer)', 'EXECUTE')",
                (role,),
            )
            assert cur.fetchone()[0] is want, f"grant mismatch for {role}"
        cur.execute(
            "SELECT count(*) FROM information_schema.table_constraints "
            "WHERE table_schema = 'public' AND table_name = 'listings' "
            "AND constraint_name = 'listings_reserved_quantity_check'"
        )
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public' "
            "AND indexname = 'inventory_one_active_reservation_per_item'"
        )
        assert cur.fetchone()[0] == 1
    conn.rollback()


# ---------------------------------------------------------------------------
# Test 1 — cleanup holds the order lock first.
# ---------------------------------------------------------------------------


def test_01_cleanup_first_then_confirm_reconciles(pg_session, conn):
    psycopg, pg_errors = pg_session
    fx = make_fixture(conn, n_items=2, qty=2, expired=True, tx_status="created")
    order, tx, listings = fx["order"], fx["tx"], fx["listings"]
    driver = _connect(psycopg, application_name="w912-driver")
    try:
        with driver.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (BARRIER_KEY,))
        set_barrier(conn, "expire")
        observer = _connect(psycopg, application_name="w912-observer")
        observer.autocommit = True
        # Each poll must see current backends: pg_stat_activity reads
        # inside one open transaction do not reflect backends that
        # connected after the transaction's first pg_stat_activity
        # read, so the observer runs in autocommit (one txn per poll).
        try:

            def cleanup_work(c):
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT public.backend_release_expired_reservations_v2(100)"
                    )
                    (result,) = cur.fetchone()
                c.commit()
                return result

            t_clean = SessionThread(pg_session, cleanup_work, "w912-A")
            t_clean.start()
            pid_a = wait_until(
                "cleanup session A registered in pg_stat_activity",
                lambda: _pid_by_app(observer, "w912-A"),
            )
            wait_blocked(observer, pid_a, "cleanup paused at barrier")
            # A holds the order lock (relation lock) while paused.
            assert any(
                r["relname"] == "orders" and r["granted"]
                for r in locks_for(observer, pid_a)
            ), "cleanup does not hold the orders lock while paused"

            def confirm_work(c):
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT public.backend_confirm_payment_capture(%s, %s, %s, true)",
                        (tx, "pay-test1-" + uuid.uuid4().hex[:8], Decimal("100")),
                    )
                    (result,) = cur.fetchone()
                c.commit()
                return result

            t_conf = SessionThread(pg_session, confirm_work, "w912-B")
            t_conf.start()
            pid_b = wait_until(
                "confirm session B registered in pg_stat_activity",
                lambda: _pid_by_app(observer, "w912-B"),
            )
            wait_blocked(observer, pid_b, "confirm blocked behind cleanup")
            wait_for_transaction(
                observer, pid_b, pid_a, "confirm waiting on cleanup's transaction"
            )
            # Release the barrier: cleanup finishes and commits first.
            with driver.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (BARRIER_KEY,))
            t_clean.join(timeout=30)
            assert not t_clean.is_alive(), "cleanup thread did not finish"
            assert t_clean.error is None, f"cleanup raised: {t_clean.error!r}"
            assert t_clean.result["released"] == 2, t_clean.result
            t_conf.join(timeout=30)
            assert not t_conf.is_alive(), "confirm thread did not finish"
            assert t_conf.error is None, f"confirm raised: {t_conf.error!r}"
            assert str(t_conf.result) == order  # confirm returns a UUID object
        finally:
            observer.close()
    finally:
        clear_barrier(conn)
        driver.close()
    # Cleanup released the stock and expired the order; confirmation must
    # NOT have confirmed it, and must have routed to reconciliation.
    assert fetch_order(conn, order) == ("expired", "reconciliation_required")
    assert fetch_tx(conn, tx)[0] == "reconciliation_required"
    assert fetch_tx(conn, tx)[1] == "RESERVATION_NOT_ACTIVE_OR_INCOMPLETE"
    for lid in listings:
        assert fetch_listing(conn, lid)[1] == 0  # reserved back to zero
    assert count_events(conn, order, "reservation_released") == 2
    assert count_events(conn, order, "sold") == 0
    assert count_order_events(conn, order, "confirmed") == 0
    assert count_order_events(conn, order, "expired") == 1
    # Late-payment retry: a second confirm is a no-op, not a confirmation.
    before = count_events(conn, order, "reservation_released")
    call_confirm(conn, tx, "pay-test1-retry-" + uuid.uuid4().hex[:8])
    assert fetch_order(conn, order) == ("expired", "reconciliation_required")
    assert count_events(conn, order, "reservation_released") == before
    assert count_order_events(conn, order, "confirmed") == 0
    assert_invariants(conn, listings, [order])


def _pids_by_app(observer, app_name: str):
    with observer.cursor() as cur:
        cur.execute(
            "SELECT pid FROM pg_stat_activity WHERE application_name = %s", (app_name,)
        )
        return cur.fetchall()


def _pid_by_app(observer, app_name: str):
    rows = _pids_by_app(observer, app_name)
    return rows[0][0] if rows else None


# ---------------------------------------------------------------------------
# Test 2 — confirmation holds the order lock first; cleanup skips.
# ---------------------------------------------------------------------------


def test_02_confirm_first_then_cleanup_skips(pg_session, conn):
    psycopg, pg_errors = pg_session
    fx = make_fixture(conn, n_items=1, qty=3, expired=False, tx_status="created")
    order, tx, listings = fx["order"], fx["tx"], fx["listings"]
    driver = _connect(psycopg, application_name="w912-driver")
    try:
        with driver.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (BARRIER_KEY,))
        set_barrier(conn, "consume")
        observer = _connect(psycopg, application_name="w912-observer")
        observer.autocommit = True
        # Each poll must see current backends: pg_stat_activity reads
        # inside one open transaction do not reflect backends that
        # connected after the transaction's first pg_stat_activity
        # read, so the observer runs in autocommit (one txn per poll).
        try:

            def confirm_work(c):
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT public.backend_confirm_payment_capture(%s, %s, %s, true)",
                        (tx, "pay-test2-" + uuid.uuid4().hex[:8], Decimal("100")),
                    )
                    (result,) = cur.fetchone()
                c.commit()
                return result

            t_conf = SessionThread(pg_session, confirm_work, "w912-A")
            t_conf.start()
            pid_a = wait_until(
                "confirm session A registered",
                lambda: _pid_by_app(observer, "w912-A"),
            )
            wait_blocked(observer, pid_a, "confirm paused at barrier")
            assert any(
                r["relname"] == "orders" and r["granted"]
                for r in locks_for(observer, pid_a)
            ), "confirm does not hold the orders lock while paused"

            # Cleanup must SKIP the locked order (not block, not deadlock).
            def cleanup_work(c):
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT public.backend_release_expired_reservations_v2(100)"
                    )
                    (result,) = cur.fetchone()
                c.commit()
                return result

            t_clean = SessionThread(pg_session, cleanup_work, "w912-B")
            t_clean.start()
            t_clean.join(timeout=20)
            assert not t_clean.is_alive(), "cleanup blocked instead of skipping"
            assert t_clean.error is None, f"cleanup raised: {t_clean.error!r}"
            assert t_clean.result["released"] == 0, t_clean.result

            with driver.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (BARRIER_KEY,))
            t_conf.join(timeout=30)
            assert not t_conf.is_alive(), "confirm thread did not finish"
            assert t_conf.error is None, f"confirm raised: {t_conf.error!r}"
            assert str(t_conf.result) == order  # confirm returns a UUID object
        finally:
            observer.close()
    finally:
        clear_barrier(conn)
        driver.close()
    assert fetch_order(conn, order) == ("confirmed", "captured")
    assert fetch_tx(conn, tx)[0] == "captured"
    assert fetch_listing(conn, listings[0]) == (100, 0, 3, 97)
    assert count_events(conn, order, "sold") == 1
    assert count_events(conn, order, "reservation_released") == 0
    # Cleanup after confirmation must not touch the confirmed order.
    assert call_cleanup(conn)["released"] == 0
    assert count_events(conn, order, "reservation_released") == 0
    assert_invariants(conn, listings, [order])


# ---------------------------------------------------------------------------
# Test 3 — two cleanup workers, one order, repeated.
# ---------------------------------------------------------------------------


def test_03_two_workers_same_order(pg_session, conn):
    for _ in range(25):
        fx = make_fixture(conn, n_items=2, qty=2, expired=True, tx_status=None)
        order, listings = fx["order"], fx["listings"]

        def cleanup_work(c):
            with c.cursor() as cur:
                cur.execute(
                    "SELECT public.backend_release_expired_reservations_v2(100)"
                )
                (result,) = cur.fetchone()
            c.commit()
            return result

        t1 = SessionThread(pg_session, cleanup_work, "w912-W1")
        t2 = SessionThread(pg_session, cleanup_work, "w912-W2")
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)
        assert not t1.is_alive() and not t2.is_alive(), "worker thread hung"
        assert t1.error is None and t2.error is None, (t1.error, t2.error)
        total = t1.result["released"] + t2.result["released"]
        assert total == 2, (t1.result, t2.result)
        assert count_events(conn, order, "reservation_released") == 2
        assert count_order_events(conn, order, "expired") == 1
        assert fetch_order(conn, order)[0] == "expired"
        for lid in listings:
            assert fetch_listing(conn, lid)[1] == 0
        assert_invariants(conn, listings, [order])


# ---------------------------------------------------------------------------
# Test 4 — duplicate cleanup, rollback atomicity, induced-failure retry.
# ---------------------------------------------------------------------------


def test_04_duplicate_cleanup_rollback_and_retry(pg_session, conn):
    psycopg, pg_errors = pg_session
    fx = make_fixture(conn, n_items=2, qty=2, expired=True, tx_status="failed")
    order, _listings = fx["order"], fx["listings"]
    first = call_cleanup(conn)
    assert first["released"] == 2 and first["orders_expired"] == 1, first
    second = call_cleanup(conn)
    assert second == {
        "released": 0,
        "orders_expired": 0,
        "orders_preserved_reconciliation": 0,
    }, second
    assert count_events(conn, order, "reservation_released") == 2
    assert count_order_events(conn, order, "expired") == 1

    # Rollback atomicity: run cleanup inside a transaction, then roll back.
    fx2 = make_fixture(conn, n_items=1, qty=4, expired=True, tx_status=None)
    order2, listings2 = fx2["order"], fx2["listings"]
    tx_conn = _connect(psycopg, application_name="w912-rollback")
    try:
        with tx_conn.cursor() as cur:
            cur.execute("SELECT public.backend_release_expired_reservations_v2(100)")
            (result,) = cur.fetchone()
            assert result["released"] == 1
            cur.execute(
                "SELECT status FROM public.inventory_reservations WHERE order_id = %s",
                (order2,),
            )
            assert cur.fetchone()[0] == "expired"
        tx_conn.rollback()
    finally:
        tx_conn.close()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, released_at FROM public.inventory_reservations "
            "WHERE order_id = %s",
            (order2,),
        )
        status, released_at = cur.fetchone()
        assert status == "active" and released_at is None
        cur.execute(
            "SELECT count(*) FROM public.inventory_events WHERE order_id = %s",
            (order2,),
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT reserved_quantity FROM public.listings WHERE id = %s",
            (listings2[0],),
        )
        assert cur.fetchone()[0] == 4
    conn.rollback()

    # Induced failure on the second release: whole batch rolls back.
    fx3 = make_fixture(conn, n_items=2, qty=2, expired=True, tx_status=None)
    order3, listings3 = fx3["order"], fx3["listings"]
    with conn.cursor() as cur:
        cur.execute("UPDATE public.test_ctl SET value = '1' WHERE key = 'fail_enabled'")
        cur.execute(
            "UPDATE public.test_ctl SET value = %s WHERE key = 'fail_order_id'",
            (order3,),
        )
    conn.commit()
    with pytest.raises(pg_errors.RaiseException):
        call_cleanup(conn)
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("UPDATE public.test_ctl SET value = '0' WHERE key = 'fail_enabled'")
        cur.execute("UPDATE public.test_ctl SET value = '' WHERE key = 'fail_order_id'")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM public.inventory_reservations WHERE order_id = %s "
            "AND status = 'active'",
            (order3,),
        )
        assert cur.fetchone()[0] == 2
        cur.execute(
            "SELECT count(*) FROM public.inventory_events WHERE order_id = %s",
            (order3,),
        )
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT status FROM public.orders WHERE id = %s", (order3,))
        assert cur.fetchone()[0] == "pending_payment"
    conn.rollback()
    # The retry is global: it also expires order2, whose cleanup was
    # rolled back above and is still eligible. That is correct batch
    # behaviour, so assert order3's own outcome precisely instead of
    # exact global counts.
    retry = call_cleanup(conn)
    assert retry["released"] >= 2, retry
    assert fetch_order(conn, order3) == ("expired", "failed")
    assert fetch_order(conn, order2) == ("expired", "failed")
    assert count_events(conn, order3, "reservation_released") == 2
    assert_invariants(conn, listings3, [order3])


# ---------------------------------------------------------------------------
# Test 5 — bounded batch behaviour.
# ---------------------------------------------------------------------------


def test_05_bounded_batch(pg_session, conn):
    psycopg, pg_errors = pg_session
    fx = make_fixture(conn, n_items=5, qty=1, expired=True, tx_status=None)
    order, listings = fx["order"], fx["listings"]
    r1 = call_cleanup(conn, limit=2)
    assert r1["released"] == 2 and r1["orders_expired"] == 0, r1
    assert fetch_order(conn, order)[0] == "pending_payment"
    r2 = call_cleanup(conn, limit=2)
    assert r2["released"] == 2 and r2["orders_expired"] == 0, r2
    r3 = call_cleanup(conn, limit=2)
    assert r3["released"] == 1 and r3["orders_expired"] == 1, r3
    assert fetch_order(conn, order)[0] == "expired"
    assert count_events(conn, order, "reservation_released") == 5
    assert_invariants(conn, listings, [order])

    # Multiple orders share one budget; invalid limits raise 22023.
    fx_a = make_fixture(conn, n_items=2, qty=1, expired=True, tx_status=None)
    fx_b = make_fixture(conn, n_items=2, qty=1, expired=True, tx_status=None)
    shared = call_cleanup(conn, limit=3)
    assert shared["released"] == 3, shared
    rest = call_cleanup(conn, limit=1000)
    assert rest["released"] == 1, rest
    assert call_cleanup(conn, limit=1)["released"] == 0
    for bad in (0, 1001):
        with pytest.raises(Exception) as excinfo:
            call_cleanup(conn, limit=bad)
        err = excinfo.value
        assert "invalid_batch_limit" in str(err), err
        assert getattr(getattr(err, "diag", None), "sqlstate", None) == "22023", err
        conn.rollback()
    assert_invariants(
        conn, fx_a["listings"] + fx_b["listings"], [fx_a["order"], fx_b["order"]]
    )


# ---------------------------------------------------------------------------
# Test 6 — payment-status tiers.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tx_status,expected",
    [
        ("authorized", "block"),
        ("captured", "block"),
        ("refunded", "block"),
        ("partially_refunded", "block"),
        ("reconciliation_required", "preserve"),
        (None, "expire"),
        ("created", "expire"),
        ("failed", "expire"),
    ],
)
def test_06_payment_tiers(pg_session, conn, tx_status, expected):
    order_payment = (
        "reconciliation_required"
        if tx_status == "reconciliation_required"
        else "created"
    )
    fx = make_fixture(
        conn,
        n_items=2,
        qty=2,
        expired=True,
        tx_status=tx_status,
        order_payment_status=order_payment,
    )
    order, listings = fx["order"], fx["listings"]
    result = call_cleanup(conn)
    if expected == "block":
        assert result["released"] == 0, result
        assert fetch_order(conn, order) == ("pending_payment", order_payment)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM public.inventory_reservations "
                "WHERE order_id = %s AND status = 'active'",
                (order,),
            )
            assert cur.fetchone()[0] == 2
        for lid in listings:
            assert fetch_listing(conn, lid)[1] == 2
        assert count_events(conn, order, "reservation_released") == 0
    elif expected == "preserve":
        assert result["released"] == 2, result
        assert result["orders_preserved_reconciliation"] == 1, result
        assert result["orders_expired"] == 0, result
        # Order row untouched: finance still sees reconciliation_required.
        assert fetch_order(conn, order) == (
            "pending_payment",
            "reconciliation_required",
        )
        assert (
            count_events(
                conn,
                order,
                "reservation_released",
                "reservation_expired_reconciliation_pending",
            )
            == 2
        )
    else:
        assert result["released"] == 2, result
        assert result["orders_expired"] == 1, result
        assert fetch_order(conn, order) == ("expired", "failed")
        assert (
            count_events(
                conn,
                order,
                "reservation_released",
                "reservation_expired_after_payment_failure_or_no_payment",
            )
            == 2
        )
    assert_invariants(conn, listings, [order])


# ---------------------------------------------------------------------------
# Test 7 — residual listing-lock contention (two cleanups, opposite order).
# ---------------------------------------------------------------------------


def test_07_listing_lock_contention(pg_session, conn):
    psycopg, pg_errors = pg_session
    # Sequential baseline first: no contention, no deadlock.
    make_fixture(conn, n_items=1, qty=1, expired=True, tx_status=None)
    assert call_cleanup(conn)["released"] == 1

    # Shared listings; X expires L2 before L1, Y expires L1 before L2.
    shared = []
    probe = _connect(psycopg, application_name="w912-setup")
    try:
        base = make_fixture(probe, n_items=0, tx_status=None)
        for _ in range(2):
            lid = uid()
            with probe.cursor() as cur:
                cur.execute(
                    "INSERT INTO public.listings (id, store_id, listing_type, "
                    "title, reference_value, selling_price, total_quantity, "
                    "reserved_quantity, sold_quantity, sale_starts_at, "
                    "sale_ends_at, pickup_starts_at, pickup_ends_at, "
                    "created_by) VALUES (%s, %s, 'surprise_bag', 'Bag', 100, "
                    "50, 100, 0, 0, now() - interval '1 hour', "
                    "now() + interval '2 hours', now(), "
                    "now() + interval '3 hours', %s)",
                    (lid, base["store"], base["customer"]),
                )
            shared.append(lid)
        probe.commit()
    finally:
        probe.close()
    l1, l2 = shared
    # X: L2 expires -10min, L1 expires -5min. Y: L1 -10min, L2 -5min.
    # Build via make_fixture with shared listings + explicit offsets:
    # items map onto listings in order, so X needs [L2, L1] order and Y
    # needs [L1, L2] order. make_fixture maps items[i] -> listings[i % n],
    # so pass the listings in the desired processing order per order.
    fx_x = _make_order_on_listings(conn, [l2, l1], [-10, -5])
    # Y starts INELIGIBLE (expires in the future) and is expired only
    # after X is already paused: a single cleanup call claims every
    # currently-eligible order, so starting both workers together lets
    # the first caller take both orders and leaves the second with no
    # work. Staging eligibility gives each worker exactly one order.
    fx_y = _make_order_on_listings(conn, [l1, l2], [60, 60])
    order_x, order_y = fx_x["order"], fx_y["order"]

    driver = _connect(psycopg, application_name="w912-driver")
    try:
        with driver.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (BARRIER_KEY,))
        set_barrier(conn, "listing")
        observer = _connect(psycopg, application_name="w912-observer")
        observer.autocommit = True
        # Each poll must see current backends: pg_stat_activity reads
        # inside one open transaction do not reflect backends that
        # connected after the transaction's first pg_stat_activity
        # read, so the observer runs in autocommit (one txn per poll).
        try:

            def cleanup_work(c):
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT public.backend_release_expired_reservations_v2(100)"
                    )
                    (result,) = cur.fetchone()
                c.commit()
                return result

            tx_ = SessionThread(pg_session, cleanup_work, "w912-X")
            ty = SessionThread(pg_session, cleanup_work, "w912-Y")
            tx_.start()
            pid_x = wait_until(
                "worker X registered",
                lambda: _pid_by_app(observer, "w912-X"),
            )
            wait_blocked(observer, pid_x, "worker X paused on first listing")
            # X holds order X only (Y was ineligible at X's claim).
            # Expire Y now so Y claims exactly order Y.
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.inventory_reservations SET expires_at = "
                    "now() - interval '10 minutes' WHERE order_id = %s",
                    (order_y,),
                )
            conn.commit()
            ty.start()
            pid_y = wait_until(
                "worker Y registered",
                lambda: _pid_by_app(observer, "w912-Y"),
            )
            wait_blocked(observer, pid_y, "worker Y paused on first listing")
            with driver.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (BARRIER_KEY,))
            tx_.join(timeout=30)
            ty.join(timeout=30)
            assert not tx_.is_alive() and not ty.is_alive(), "worker hung"
        finally:
            observer.close()
    finally:
        clear_barrier(conn)
        driver.close()

    deadlocks = [t for t in (tx_, ty) if t.error is not None]
    [t for t in (tx_, ty) if t.error is None]
    # Either the deadlock reproduced (exactly one 40P01 abort, fully
    # rolled back) or both completed without contention. Both outcomes
    # are recorded; only a partial/corrupt outcome fails.
    if deadlocks:
        assert len(deadlocks) == 1, [t.error for t in (tx_, ty)]
        err_text = str(deadlocks[0].error)
        assert "40P01" in err_text or "deadlock" in err_text.lower(), err_text
        print("listing deadlock reproduced: one worker aborted with 40P01")
    else:
        print(
            "listing deadlock did NOT reproduce in this run "
            "(both workers completed); see report section 8"
        )
    # The aborted worker (if any) must have left zero partial effects.
    for order in (order_x, order_y):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM public.inventory_events WHERE order_id = %s "
                "AND event_type = 'reservation_released'",
                (order,),
            )
            released_events = cur.fetchone()[0]
        status, _ = fetch_order(conn, order)
        if released_events == 0:
            assert status == "pending_payment", (
                f"aborted worker left order {order} in {status} without events"
            )
    # Retry the unfinished order (if any) to completion; final state
    # must be fully consistent either way.
    retry = call_cleanup(conn)
    assert retry["released"] in (0, 2), retry
    for order in (order_x, order_y):
        assert fetch_order(conn, order)[0] == "expired"
        assert count_events(conn, order, "reservation_released") == 2
        assert count_order_events(conn, order, "expired") == 1
    for lid in shared:
        assert fetch_listing(conn, lid)[1] == 0
    assert_invariants(conn, shared, [order_x, order_y])


def _make_order_on_listings(conn, listings_in_processing_order, offsets_min):
    """Build one order whose reservations map onto the given listings in
    the given order, with the given expiry offsets (minutes, negative =
    already expired). Reuses make_fixture's shared_listings mapping
    (items[i] -> listings[i])."""
    n = len(listings_in_processing_order)
    fx = make_fixture(
        conn,
        n_items=n,
        qty=1,
        expired=True,
        tx_status=None,
        shared_listings=listings_in_processing_order,
        expiry_offsets_min=offsets_min,
    )
    return fx
