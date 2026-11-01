"""Standalone expired-reservation cleanup worker (W9.1).

What it does, and what it does not do:

- Each pass calls exactly one bounded database operation:
  backend_release_expired_reservations_v2 (one batch of at
  most --batch-size expired reservations, default 100,
  clamped to 1-1000 server-side). All tier, locking, and
  idempotency semantics live in that SQL function, not
  here. This process is a thin, restartable driver: it
  holds no queue state, so killing it loses nothing
  (unclaimed rows stay active; a partially processed
  batch is picked up by the next pass, because only
  'active' rows are ever selected).
- Safe to run once (--once, for a scheduler),
  repeatedly, and concurrently: concurrent workers claim
  disjoint reservation sets (FOR UPDATE SKIP LOCKED),
  and a reservation released by one pass is never
  re-processed by another (it is no longer 'active').
- This worker NEVER touches payments: it never confirms,
  fails, or refunds anything, and it never calls the v1
  cleanup (backend_release_expired_reservations), which
  has no tier rules and would leave 'created' stock
  stuck. Money states are decided only by the payment
  lifecycle (confirm / mark-failed / reconciliation);
  this worker only frees stock whose reservation has
  already time-expired and whose order can no longer
  confirm (see the migration header for the trace).
- Logs only counts — never order ids, user ids, amounts,
  or keys.

Deployment (NOT done by this milestone — no worker or
scheduler is configured here):
- Long-running: run this process continuously with the
  backend's environment (SUPABASE_URL,
  SUPABASE_PUBLISHABLE_KEY, SUPABASE_SERVICE_ROLE_KEY).
  It polls every --interval-seconds (default 60).
- Scheduled: run with --once from a cron job every 15
  minutes. --once exits 0 on a successful pass and 1 if
  the RPC call fails, so the scheduler can alert.
- The migration file for the v2 RPC is NOT applied to
  live by this milestone. Until it is applied through
  the approved process, this worker's RPC call will
  fail (unknown function) and --once will exit 1 — that
  failure is the correct signal, not something to work
  around by calling v1.

Run from backend/:
  python -m app.reservation_cleanup [--once]
  [--interval-seconds 60] [--batch-size 100]
  [--worker-id NAME]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import uuid
from typing import Any, Protocol

from app.config import get_settings
from app.logging_config import configure_logging
from app.supabase_client import SupabaseRestClient, service_client

logger = logging.getLogger("savebite.reservation_cleanup")

CLEANUP_RPC = "backend_release_expired_reservations_v2"
DEFAULT_BATCH_SIZE = 100


class _RpcClient(Protocol):
    async def rpc(self, name: str, params: dict) -> Any: ...


class CleanupWorker:
    """One worker identity driving the W9.1 v2 cleanup."""

    def __init__(
        self,
        client: _RpcClient,
        *,
        worker_id: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._client = client
        self._worker_id = worker_id
        self._batch_size = batch_size

    async def run_once(self) -> dict[str, Any]:
        """One bounded pass. Returns the RPC's counts
        only. RPC failures propagate: the caller decides
        whether to retry (--once exits 1) or log and
        continue (loop mode)."""
        raw = await self._client.rpc(
            CLEANUP_RPC,
            {"p_limit": self._batch_size},
        )
        result = raw if isinstance(raw, dict) else {}
        logger.info("cleanup pass complete: %s", json.dumps(result, sort_keys=True))
        return result

    async def run_forever(self, interval_seconds: int, stop: asyncio.Event) -> None:
        """Loop until stop is set. A failed pass is logged
        and retried after the interval; it never kills the
        worker, because a transient database or network
        failure must not stop cleanup permanently."""
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001 - must survive
                logger.error(
                    "cleanup pass failed: %s: %s",
                    type(exc).__name__,
                    exc,
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SaveBite expired-reservation cleanup worker (W9.1)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single bounded cleanup batch and exit.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Seconds between passes in loop mode (default 60).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Reservations per cleanup call (default 100, clamped to 1-1000 server-side).",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default="",
        help="Worker identity for logging (default: generated).",
    )
    return parser


async def _amain(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        client: SupabaseRestClient = service_client(settings)
    except Exception as exc:
        print(
            f"reservation cleanup worker cannot start: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    worker = CleanupWorker(
        client,
        worker_id=args.worker_id or f"cleanup-{uuid.uuid4().hex[:8]}",
        batch_size=args.batch_size,
    )
    if args.once:
        try:
            result = await worker.run_once()
        except Exception as exc:
            print(
                f"reservation cleanup pass failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(json.dumps(result, sort_keys=True))
        return 0
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    logger.info("reservation cleanup worker started: id=%s", worker._worker_id)
    await worker.run_forever(args.interval_seconds, stop)
    logger.info("reservation cleanup worker stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m app.reservation_cleanup`."""
    args = build_parser().parse_args(argv)
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
