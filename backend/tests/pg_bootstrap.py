"""Bootstrap a disposable PostgreSQL test database for SaveBite W9.1.2.

What this builds (and what it deliberately does NOT do):

- A throwaway local database containing the REAL schema from the
  repository's consolidated baseline tracking copy
  (``supabase/migrations/20261031060000_remote_schema_baseline.sql``)
  plus the W9.1 migration (``20261101200000``) and the W9.1.1 migration
  (``20261102210000``), applied in chronological order.
- The actual migration-defined function bodies are used verbatim. No
  function is replaced with a simplified test version.
- NOTHING here touches live Supabase, production data, or the
  repository's migration files. The baseline file itself is never
  edited; the two deviations below live only in this script.

Documented deviations from a verbatim baseline replay (all forced by
the tracking copy, none of them touch the functions under test):

1. ``auth.users`` does not exist outside Supabase, but four baseline
   foreign keys reference it (``orders.customer_id``,
   ``audit_logs.actor_user_id``, ``commission_rules.created_by``,
   ``idempotency_records.actor_user_id``,
   ``notification_outbox.user_id``). This script pre-creates a minimal
   ``auth.users (id uuid primary key)`` table so those foreign keys
   resolve. No tested function reads ``auth.users``; functions that
   call ``auth.uid()`` (for example ``begin_payment_checkout``) are
   created but never executed by the concurrency tests, and would fail
   loudly if called, because no ``auth.uid()`` function exists here.
2. All 41 ``CREATE POLICY`` statements in the tracking copy carry a
   corrupted role list produced by the introspection
   (``to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, }``),
   which is not valid PostgreSQL. The script strips exactly those 41
   statements (and asserts the count) before applying the file. The
   tested functions are ``SECURITY DEFINER`` and run as the table
   owner, so row-level policies cannot change their behaviour; policy
   correctness is out of scope for this task and lives in the original
   15 live migrations, not in this tracking copy.
3. Two baseline columns use the PostGIS ``geography`` type
   (``stores.location``, ``platform_service_areas.boundary``). The
   script requires the PostGIS extension and fails clearly if it is
   unavailable, rather than silently building a reduced schema.
4. Constraint ordering: the tracking copy groups ``ALTER TABLE``
   constraints per table, so some foreign keys precede the primary
   key they reference (for example, ``ledger_entries``'s FK to
   ``merchants(id)`` at line 633 precedes ``merchants_pkey`` at line
   745, and PostgreSQL rejects the FK). The script therefore applies
   the baseline in two phases — everything except foreign keys, then
   all 83 foreign-key statements — without changing any statement's
   text. The live database was built by the original 15 migrations in
   dependency order, so this defect exists only in the tracking copy.
5. SQL-language functions are name-resolved at creation time, and
   several baseline functions call ``auth.uid()`` (48 references).
   The script pre-creates a fail-closed stub,
   ``auth.uid() RETURNS uuid`` returning NULL, so those functions
   can be created; any accidental call to an auth-gated function
   then refuses (``authentication_required`` / NULL checks) instead
   of silently succeeding. No tested function calls ``auth.uid()``.
6. Forward references: some SQL-language functions are defined before
   the functions they call (for example, ``can_view_order`` at line
   1138 calls ``private.has_platform_role``, defined at line 1453;
   SQL bodies are name-resolved at creation, unlike plpgsql). The
   script therefore applies phase 1 repeatedly (up to 6 passes) until
   a pass produces no error outside an allowlist of "already exists"
   / "multiple primary keys" re-run errors. A pass that makes no
   progress fails clearly with the remaining errors, so a genuine
   defect is never masked.

Roles: the W9.1/W9.1.1 migrations issue ``REVOKE``/``GRANT`` against
``anon``, ``authenticated`` and ``service_role``, so those roles are
pre-created (``NOLOGIN``) before the migrations run. That is also what
lets the grant checks in the test module verify that ``anon`` and
``authenticated`` cannot execute the protected worker RPC.

Server management: this script can start its own disposable server
(``--initdb`` path) as a non-root OS user, because ``initdb`` refuses
to run as root. If you already have a PostgreSQL server, pass
``--existing-dsn`` instead and the script only (re)creates the database
and applies the schema. Never point this script at a shared or
production database: it drops and recreates the target database.

Usage (disposable server, the default for this task)::

    python3 backend/tests/pg_bootstrap.py --pgdata /tmp/savebite-pgtest/data \
        --socket-dir /tmp/savebite-pgtest/sock --port 54399

    # afterwards, tests connect with (for example):
    #   SAVEBITE_PG_TEST_DSN="host=/tmp/savebite-pgtest/sock port=54399 \
    #       dbname=savebite_pgtest user=pgtest"

    python3 backend/tests/pg_bootstrap.py --teardown \
        --pgdata /tmp/savebite-pgtest/data --socket-dir /tmp/savebite-pgtest/sock

Usage (existing server)::

    python3 backend/tests/pg_bootstrap.py --existing-dsn \
        "host=127.0.0.1 port=5432 dbname=savebite_pgtest user=pgtest"

Requires: ``psql`` on PATH (and ``initdb``/``pg_ctl`` for the
``--initdb`` path). Exits non-zero with a clear message on any failure.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "supabase" / "migrations"
BASELINE = MIGRATIONS / "20261031060000_remote_schema_baseline.sql"
W91 = MIGRATIONS / "20261101200000_w91_reservation_expiry.sql"
W911 = MIGRATIONS / "20261102210000_w911_cleanup_lock_order.sql"

EXPECTED_STRIPPED_POLICIES = 41
DEFAULT_DBNAME = "savebite_pgtest"
DEFAULT_DBUSER = "pgtest"
DEFAULT_PORT = 54399


class BootstrapError(RuntimeError):
    """Raised when any bootstrap step fails; message states what broke."""


def _run(
    cmd: list[str], *, as_user: str | None = None, input_text: str | None = None
) -> str:
    """Run a command, returning stdout; raise BootstrapError on failure."""
    if as_user:
        cmd = ["su", as_user, "-c", " ".join(_shell_quote(c) for c in cmd)]
    proc = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
    if proc.returncode != 0:
        raise BootstrapError(
            "command failed ({}): {}\nstdout: {}\nstderr: {}".format(
                proc.returncode, " ".join(cmd), proc.stdout[-2000:], proc.stderr[-2000:]
            )
        )
    return proc.stdout


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _pg_bin_dir() -> str:
    """Locate the PostgreSQL binary directory (Debian puts initdb outside PATH)."""
    import glob

    found = shutil.which("initdb")
    if found:
        return os.path.dirname(found)
    candidates = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))
    if candidates:
        return os.path.dirname(candidates[0])
    raise BootstrapError(
        "initdb not found: install PostgreSQL or add its bin directory to PATH"
    )


def _which(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise BootstrapError(
            f"{name} not found on PATH. Install PostgreSQL (psql/initdb/pg_ctl) "
            "or point --existing-dsn at a running server."
        )
    return path


def prepare_baseline(sql_text: str) -> tuple[str, str, int, int]:
    """Split the baseline into (phase1_sql, deferred_fk_sql, n_policies, n_fks).

    - CREATE POLICY statements are stripped (corrupted role lists, see
      module doc); the count is asserted by the caller.
    - FOREIGN KEY statements are deferred to phase 2: the tracking copy
      groups constraints per table, so some FKs precede the primary key
      they reference. Every FK statement in this file is a single line
      starting with ``alter table``; anything else fails clearly rather
      than being guessed at.
    """
    phase1: list[str] = []
    deferred: list[str] = []
    n_policies = 0
    skipping = False
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not skipping and stripped.lower().startswith("create policy "):
            skipping = True
            n_policies += 1
        if skipping:
            if stripped.endswith(";"):
                skipping = False
            continue
        if stripped.lower().startswith("alter table") and "FOREIGN KEY" in line:
            if not stripped.endswith(";"):
                raise BootstrapError(
                    f"multi-line FOREIGN KEY statement found; refusing to guess: {line[:120]}"
                )
            deferred.append(line)
            continue
        phase1.append(line)
    if skipping:
        raise BootstrapError("unterminated CREATE POLICY statement in baseline file")
    return (
        "\n".join(phase1) + "\n",
        "\n".join(deferred) + "\n",
        n_policies,
        len(deferred),
    )


def strip_policies(sql_text: str) -> tuple[str, int]:
    """Backward-compatible helper: strip policies only (see prepare_baseline)."""
    phase1, _, n_policies, _ = prepare_baseline(sql_text)
    return phase1, n_policies


def psql_args(host: str | None, port: int | None, user: str, dbname: str) -> list[str]:
    args = ["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A"]
    if host:
        args += ["-h", host]
    if port:
        args += ["-p", str(port)]
    args += ["-U", user, "-d", dbname]
    return args


def psql_file(
    host: str | None, port: int | None, user: str, dbname: str, path: Path
) -> None:
    with open(path, encoding="utf-8") as fh:
        sql = fh.read()
    _run_psql(host, port, user, dbname, sql)


def _run_psql_loose(
    host: str | None, port: int | None, user: str, dbname: str, sql: str
) -> str:
    """Run psql WITHOUT ON_ERROR_STOP; return combined stderr.

    Used for the multi-pass phase-1 application: statements that fail
    only because a dependency is defined later in the file succeed on
    a later pass, while already-applied statements report harmless
    "already exists" errors.
    """
    args = ["psql", "-v", "ON_ERROR_STOP=0", "-q"]
    if host:
        args += ["-h", host]
    if port:
        args += ["-p", str(port)]
    args += ["-U", user, "-d", dbname]
    proc = subprocess.run(args, input=sql, capture_output=True, text=True)
    if proc.returncode != 0:
        raise BootstrapError(
            f"psql connection/command failed ({proc.returncode}): {(proc.stderr or proc.stdout).strip()[-2000:]}"
        )
    return proc.stderr or ""


def _non_allowed_errors(stderr: str) -> list[str]:
    """Extract ERROR lines that are not benign re-run duplicates."""
    allowed = ("already exists", "multiple primary keys")
    errors = []
    for line in stderr.splitlines():
        if "ERROR:" in line:
            msg = line.split("ERROR:", 1)[1].strip()
            if not any(a in msg for a in allowed):
                errors.append(msg)
    return errors


def _apply_phase1_multi_pass(
    host: str | None, port: int | None, user: str, dbname: str, phase1: str
) -> None:
    """Apply phase 1 until a pass is clean (see module doc, deviation 6)."""
    previous: list[str] | None = None
    for attempt in range(1, 7):
        stderr = _run_psql_loose(host, port, user, dbname, phase1)
        errors = _non_allowed_errors(stderr)
        if not errors:
            return
        if errors == previous:
            raise BootstrapError(
                "baseline phase 1 stalled after {} passes; remaining errors:\n{}".format(
                    attempt, "\n".join(errors[:10])
                )
            )
        previous = errors
    raise BootstrapError(
        "baseline phase 1 did not converge after 6 passes; remaining errors:\n{}".format(
            "\n".join(previous[:10] if previous else [])
        )
    )


def _run_psql(
    host: str | None, port: int | None, user: str, dbname: str, sql: str
) -> str:
    cmd = psql_args(host, port, user, dbname)
    proc = subprocess.run(cmd, input=sql, capture_output=True, text=True)
    if proc.returncode != 0:
        raise BootstrapError(
            f"psql failed (db={dbname}):\nstdout: {proc.stdout[-2000:]}\nstderr: {proc.stderr[-2000:]}"
        )
    return proc.stdout


def pre_steps_sql() -> str:
    return """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN;
  END IF;
END $$;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;
"""


def verification_sql() -> str:
    return """
SELECT 'func:private.release_expired_reservations_v2='
  || count(*) FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'private' AND p.proname = 'release_expired_reservations_v2';
SELECT 'func:public.backend_release_expired_reservations_v2='
  || count(*) FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'backend_release_expired_reservations_v2';
SELECT 'func:private.confirm_payment_capture='
  || count(*) FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'private' AND p.proname = 'confirm_payment_capture';
SELECT 'func:public.backend_confirm_payment_capture='
  || count(*) FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'backend_confirm_payment_capture';
SELECT 'priv:anon=' || has_function_privilege(
  'anon', 'public.backend_release_expired_reservations_v2(integer)', 'EXECUTE');
SELECT 'priv:authenticated=' || has_function_privilege(
  'authenticated', 'public.backend_release_expired_reservations_v2(integer)', 'EXECUTE');
SELECT 'priv:service_role=' || has_function_privilege(
  'service_role', 'public.backend_release_expired_reservations_v2(integer)', 'EXECUTE');
SELECT 'table:orders=' || count(*) FROM information_schema.tables
  WHERE table_schema = 'public' AND table_name = 'orders';
SELECT 'table:inventory_reservations=' || count(*) FROM information_schema.tables
  WHERE table_schema = 'public' AND table_name = 'inventory_reservations';
SELECT 'table:listings=' || count(*) FROM information_schema.tables
  WHERE table_schema = 'public' AND table_name = 'listings';
SELECT 'table:payment_transactions=' || count(*) FROM information_schema.tables
  WHERE table_schema = 'private' AND table_name = 'payment_transactions';
SELECT 'version:' || version();
"""


def apply_schema(
    host: str | None, port: int | None, user: str, dbname: str
) -> dict[str, str]:
    """Apply pre-steps, baseline (policies stripped), W9.1, W9.1.1; verify."""
    for path in (BASELINE, W91, W911):
        if not path.exists():
            raise BootstrapError(f"migration file missing: {path}")
    _run_psql(host, port, user, dbname, pre_steps_sql())
    phase1, deferred_fks, stripped, n_fks = prepare_baseline(
        BASELINE.read_text(encoding="utf-8")
    )
    if stripped != EXPECTED_STRIPPED_POLICIES:
        raise BootstrapError(
            f"expected {EXPECTED_STRIPPED_POLICIES} CREATE POLICY statements to strip from the baseline, "
            f"found {stripped}; the file changed, refusing to guess"
        )
    if n_fks == 0:
        raise BootstrapError("expected foreign-key statements to defer, found none")
    _apply_phase1_multi_pass(host, port, user, dbname, phase1)
    _run_psql(host, port, user, dbname, deferred_fks)
    psql_file(host, port, user, dbname, W91)
    psql_file(host, port, user, dbname, W911)
    out = _run_psql(host, port, user, dbname, verification_sql())
    checks: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("version:"):
            checks["version"] = line[len("version:") :]
        elif "=" in line:
            key, value = line.split("=", 1)
            checks[key] = value
    expected = {
        "func:private.release_expired_reservations_v2": "1",
        "func:public.backend_release_expired_reservations_v2": "1",
        "func:private.confirm_payment_capture": "1",
        "func:public.backend_confirm_payment_capture": "1",
        "priv:anon": "false",
        "priv:authenticated": "false",
        "priv:service_role": "true",
        "table:orders": "1",
        "table:inventory_reservations": "1",
        "table:listings": "1",
        "table:payment_transactions": "1",
    }
    for key, want in expected.items():
        got = checks.get(key)
        if got != want:
            raise BootstrapError(
                f"verification failed: {key} expected {want}, got {got} (full checks: {checks})"
            )
    return checks


def ensure_os_user(username: str) -> None:
    """Create a non-root OS user for initdb (initdb refuses to run as root)."""
    proc = subprocess.run(["id", username], capture_output=True, text=True)
    if proc.returncode == 0:
        return
    if os.geteuid() != 0:
        raise BootstrapError(
            f"OS user {username} does not exist and this process is not root, so it "
            f"cannot be created. Create it first (useradd {username}) or pass "
            "--existing-dsn."
        )
    _run(["useradd", "--no-create-home", "--shell", "/bin/bash", username])


def start_disposable_server(
    pgdata: Path, socket_dir: Path, port: int, os_user: str
) -> None:
    """initdb (if needed) and start a socket-only disposable server."""
    _which("initdb")
    _which("pg_ctl")
    _which("pg_isready")
    socket_dir.mkdir(parents=True, exist_ok=True)
    _run(["chown", f"{os_user}:{os_user}", str(socket_dir)])
    # Idempotency: a previous bootstrap run may have left the server up
    # (for example, if schema application failed after start).
    ready = subprocess.run(
        [
            "su",
            "-s",
            "/bin/bash",
            os_user,
            "-c",
            " ".join(
                [
                    _shell_quote("pg_isready"),
                    "-h",
                    _shell_quote(str(socket_dir)),
                    "-p",
                    str(port),
                ]
            ),
        ],
        capture_output=True,
        text=True,
    )
    if ready.returncode == 0 and (pgdata / "PG_VERSION").exists():
        return
    if not (pgdata / "PG_VERSION").exists():
        pgdata.parent.mkdir(parents=True, exist_ok=True)
        _run(["chown", f"{os_user}:{os_user}", str(pgdata.parent)])
        _run(
            [
                "su",
                "-s",
                "/bin/bash",
                os_user,
                "-c",
                " ".join(
                    [
                        _shell_quote("initdb"),
                        "-D",
                        _shell_quote(str(pgdata)),
                        "--auth=trust",
                        "--no-instructions",
                    ]
                ),
            ]
        )
    conf = pgdata / "postgresql.conf"
    conf_text = conf.read_text(encoding="utf-8") if conf.exists() else ""
    if "W9.1.2 disposable test server" not in conf_text:
        with open(conf, "a", encoding="utf-8") as fh:
            fh.write("\n# W9.1.2 disposable test server (added by pg_bootstrap.py)\n")
            fh.write("listen_addresses = ''\n")
            fh.write(f"unix_socket_directories = '{socket_dir}'\n")
            fh.write(f"port = {port}\n")
    hba = pgdata / "pg_hba.conf"
    hba_text = hba.read_text(encoding="utf-8") if hba.exists() else ""
    if "W9.1.2 disposable test server" not in hba_text:
        with open(hba, "a", encoding="utf-8") as fh:
            fh.write("\n# W9.1.2 disposable test server: local trust only\n")
            fh.write("local all all trust\n")
    _run(["chown", "-R", f"{os_user}:{os_user}", str(pgdata)])
    _run(
        [
            "su",
            "-s",
            "/bin/bash",
            os_user,
            "-c",
            " ".join(
                [
                    _shell_quote("pg_ctl"),
                    "-D",
                    _shell_quote(str(pgdata)),
                    "-l",
                    _shell_quote(str(pgdata / "server.log")),
                    "start",
                ]
            ),
        ]
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        proc = subprocess.run(
            [
                "su",
                "-s",
                "/bin/bash",
                os_user,
                "-c",
                " ".join(
                    [
                        _shell_quote("pg_isready"),
                        "-h",
                        _shell_quote(str(socket_dir)),
                        "-p",
                        str(port),
                    ]
                ),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return
        time.sleep(0.5)
    raise BootstrapError("disposable server did not become ready within 60s")


def stop_disposable_server(pgdata: Path, os_user: str) -> None:
    if (pgdata / "PG_VERSION").exists():
        _run(
            [
                "su",
                "-s",
                "/bin/bash",
                os_user,
                "-c",
                " ".join(
                    [
                        _shell_quote("pg_ctl"),
                        "-D",
                        _shell_quote(str(pgdata)),
                        "stop",
                        "-m",
                        "fast",
                    ]
                ),
            ]
        )


def parse_dsn(dsn: str) -> tuple[str | None, int | None, str, str]:
    """Parse a libpq keyword/value DSN into (host, port, user, dbname)."""
    kv: dict[str, str] = {}
    for token in re.findall(r"(\w+)=('(?:[^']|'')*'|\S+)", dsn):
        key, raw = token
        kv[key] = raw[1:-1].replace("''", "'") if raw.startswith("'") else raw
    host = kv.get("host")
    port = int(kv["port"]) if kv.get("port") else None
    user = kv.get("user") or os.environ.get("USER", "postgres")
    dbname = kv.get("dbname") or DEFAULT_DBNAME
    return host, port, user, dbname


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pgdata", default="/tmp/savebite-pgtest/data")
    parser.add_argument("--socket-dir", default="/tmp/savebite-pgtest/sock")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dbname", default=DEFAULT_DBNAME)
    parser.add_argument("--os-user", default="pgtest")
    parser.add_argument(
        "--existing-dsn",
        default=None,
        help="use an existing server instead of starting one",
    )
    parser.add_argument(
        "--teardown",
        action="store_true",
        help="stop the disposable server and remove its data",
    )
    args = parser.parse_args(argv)

    try:
        bindir = _pg_bin_dir()
        os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
        if args.teardown:
            stop_disposable_server(Path(args.pgdata), args.os_user)
            shutil.rmtree(args.pgdata, ignore_errors=True)
            shutil.rmtree(args.socket_dir, ignore_errors=True)
            print("teardown complete")
            return 0

        if args.existing_dsn:
            host, port, user, dbname = parse_dsn(args.existing_dsn)
            _run_psql(
                host,
                port,
                user,
                "postgres",
                f"DROP DATABASE IF EXISTS {dbname}; CREATE DATABASE {dbname};",
            )
            checks = apply_schema(host, port, user, dbname)
        else:
            _which("psql")
            ensure_os_user(args.os_user)
            pgdata = Path(args.pgdata)
            socket_dir = Path(args.socket_dir)
            start_disposable_server(pgdata, socket_dir, args.port, args.os_user)
            host, port, user, dbname = (
                str(socket_dir),
                args.port,
                args.os_user,
                args.dbname,
            )
            _run_psql(
                host,
                port,
                user,
                "postgres",
                f"DROP DATABASE IF EXISTS {dbname}; CREATE DATABASE {dbname};",
            )
            checks = apply_schema(host, port, user, dbname)
        print("bootstrap OK")
        for key in sorted(checks):
            print(f"  {key} = {checks[key]}")
        return 0
    except BootstrapError as exc:
        print(f"bootstrap FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
