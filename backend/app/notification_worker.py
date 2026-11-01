"""Standalone notification outbox worker (W7).

What it does, and what it does not do:

- Each pass does exactly two things, in order: enqueue due
  pickup reminders (backend_enqueue_pickup_reminders, which
  is idempotent), then claim and deliver one bounded batch
  of 'in_app' outbox jobs (backend_process_notification_
  outbox). All reliability semantics — claim with expiry,
  bounded retries with backoff, dead-letter after 5
  attempts, preference checks at delivery, dedup on
  delivery — live in those database functions, not here.
  This process is a thin, restartable driver: it holds no
  queue state, so killing it loses nothing (unclaimed jobs
  stay pending; claimed jobs are reclaimed after the
  10-minute claim window).
- Safe to run once (--once, for a scheduler), repeatedly,
  and concurrently: concurrent workers claim disjoint job
  sets (FOR UPDATE SKIP LOCKED) and delivery is dedup-safe.
- Logs only counts and worker ids — never notification
  titles, bodies, user ids, tokens, or keys.

Deployment (NOT done by this milestone — no worker or
scheduler is configured here):
- Long-running: run this process continuously (e.g. a
  Render Background Worker) with the backend's environment
  (SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY,
  SUPABASE_SERVICE_ROLE_KEY). It polls every
  --interval-seconds (default 60).
- Scheduled: run with --once from a cron job every 15
  minutes. --once exits 0 on a successful pass and 1 if
  either RPC call fails, so the scheduler can alert.

Run from backend/:
  python -m app.notification_worker [--once]
  [--interval-seconds 60] [--batch-size 50]
  [--window-minutes 60] [--worker-id NAME]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from app.config import get_settings
from app.logging_config import configure_logging
from app.notifications import (
    OUTBOX_DEFAULT_BATCH_SIZE,
    REMINDER_WINDOW_MINUTES,
    WORKER_PROCESS_RPC,
    WORKER_REMINDER_RPC,
)
from app.supabase_client import SupabaseRestClient, service_client

logger = logging.getLogger("savebite.notification_worker")


class _RpcClient(Protocol):
    async def rpc(self, name: str, params: dict) -> Any: ...


class Worker:
    """One worker identity driving the W7 database functions."""

    def __init__(
        self,
        client: _RpcClient,
        *,
        worker_id: str,
        batch_size: int = OUTBOX_DEFAULT_BATCH_SIZE,
        window_minutes: int = REMINDER_WINDOW_MINUTES,
    ) -> None:
        self._client = client
        self._worker_id = worker_id
        self._batch_size = batch_size
        self._window_minutes = window_minutes

    async def run_once(self) -> dict[str, Any]:
        """One pass: enqueue reminders, then process a batch.
        Returns counts only. RPC failures propagate: the
        caller decides whether to retry (--once exits 1) or
        log and continue (loop mode)."""
        now = datetime.now(UTC).isoformat()
        raw_enqueued = await self._client.rpc(
            WORKER_REMINDER_RPC,
            {"p_now": now, "p_window_minutes": self._window_minutes},
        )
        enqueued = raw_enqueued if isinstance(raw_enqueued, int) else 0
        raw_stats = await self._client.rpc(
            WORKER_PROCESS_RPC,
            {"p_worker_id": self._worker_id, "p_batch_size": self._batch_size},
        )
        stats = raw_stats if isinstance(raw_stats, dict) else {}
        result = {"reminders_enqueued": enqueued, **stats}
        logger.info("worker pass complete: %s", json.dumps(result, sort_keys=True))
        return result

    async def run_forever(self, interval_seconds: int, stop: asyncio.Event) -> None:
        """Loop until stop is set. A failed pass is logged
        and retried after the interval; it never kills the
        worker, because a transient database or network
        failure must not stop delivery permanently."""
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001 - must survive
                logger.error(
                    "worker pass failed: %s: %s",
                    type(exc).__name__,
                    exc,
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SaveBite notification worker (W7)")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single pass (reminders + one batch) and exit.",
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
        default=OUTBOX_DEFAULT_BATCH_SIZE,
        help="Jobs per processor call (default 50, clamped to 1-200 server-side).",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=REMINDER_WINDOW_MINUTES,
        help="Pickup reminder window in minutes (default 60).",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default="",
        help="Worker identity for claim attribution (default: generated).",
    )
    return parser


async def _amain(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        client: SupabaseRestClient = service_client(settings)
    except Exception as exc:
        print(
            f"notification worker cannot start: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    worker = Worker(
        client,
        worker_id=args.worker_id or f"worker-{uuid.uuid4().hex[:8]}",
        batch_size=args.batch_size,
        window_minutes=args.window_minutes,
    )
    if args.once:
        try:
            result = await worker.run_once()
        except Exception as exc:
            print(
                f"notification worker pass failed: {type(exc).__name__}: {exc}",
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
    logger.info("notification worker started: id=%s", worker._worker_id)
    await worker.run_forever(args.interval_seconds, stop)
    logger.info("notification worker stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m app.notification_worker`."""
    args = build_parser().parse_args(argv)
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
