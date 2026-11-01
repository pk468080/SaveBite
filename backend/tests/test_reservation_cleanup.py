"""W9.1 reservation cleanup worker tests: RPC contract,
pass results, failure handling, and shutdown. The
database function itself is SQL (see the
migration-consistency tests); these tests cover only
the Python driver logic, with a fake RPC client.
They do NOT prove Postgres concurrency or the SQL tier
rules — there is no Postgres in this environment."""

import asyncio

import pytest

from app.reservation_cleanup import (
    CLEANUP_RPC,
    DEFAULT_BATCH_SIZE,
    CleanupWorker,
    build_parser,
)


class FakeRpc:
    def __init__(self, result=None, fail=False):
        self.calls = []
        self.result = result or {
            "released": 3,
            "orders_expired": 1,
            "orders_preserved_reconciliation": 0,
        }
        self.fail = fail

    async def rpc(self, name, params):
        self.calls.append((name, params))
        if self.fail:
            raise RuntimeError("upstream down")
        return dict(self.result)


@pytest.mark.asyncio
async def test_run_once_calls_v2_rpc_with_batch_limit():
    fake = FakeRpc()
    worker = CleanupWorker(fake, worker_id="cleanup-test", batch_size=25)
    result = await worker.run_once()
    assert fake.calls == [(CLEANUP_RPC, {"p_limit": 25})]
    assert result["released"] == 3
    assert result["orders_expired"] == 1
    assert result["orders_preserved_reconciliation"] == 0


@pytest.mark.asyncio
async def test_run_once_never_calls_v1_cleanup():
    fake = FakeRpc()
    worker = CleanupWorker(fake, worker_id="w")
    await worker.run_once()
    names = [name for name, _ in fake.calls]
    assert "backend_release_expired_reservations" not in names
    assert names == [CLEANUP_RPC]


@pytest.mark.asyncio
async def test_run_once_propagates_rpc_failure():
    fake = FakeRpc(fail=True)
    worker = CleanupWorker(fake, worker_id="w")
    with pytest.raises(RuntimeError):
        await worker.run_once()


@pytest.mark.asyncio
async def test_run_once_returns_empty_dict_for_non_dict_reply():
    class NullRpc(FakeRpc):
        async def rpc(self, name, params):
            self.calls.append((name, params))
            return None

    worker = CleanupWorker(NullRpc(), worker_id="w")
    assert await worker.run_once() == {}


@pytest.mark.asyncio
async def test_run_forever_stops_immediately_when_flag_set():
    fake = FakeRpc()
    worker = CleanupWorker(fake, worker_id="w")
    stop = asyncio.Event()
    stop.set()
    await worker.run_forever(60, stop)
    assert fake.calls == []


@pytest.mark.asyncio
async def test_run_forever_survives_failed_pass_then_stops():
    class Flaky(FakeRpc):
        def __init__(self, stop):
            super().__init__()
            self.stop = stop
            self.attempts = 0

        async def rpc(self, name, params):
            self.calls.append((name, params))
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("boom")
            self.stop.set()
            return dict(self.result)

    stop = asyncio.Event()
    fake = Flaky(stop)
    worker = CleanupWorker(fake, worker_id="w")
    await asyncio.wait_for(worker.run_forever(0, stop), timeout=5)
    assert fake.attempts == 2


@pytest.mark.asyncio
async def test_repeated_passes_are_independent():
    # A second pass re-calls the RPC (the driver holds no
    # state); the SQL side guarantees a released row is
    # never selected again because it is no longer
    # 'active'. Here the fake returns a shrinking count,
    # as a real second pass would after the first batch.
    class Shrinking(FakeRpc):
        def __init__(self):
            super().__init__()
            self.left = 2

        async def rpc(self, name, params):
            self.calls.append((name, params))
            released = self.left
            self.left = 0
            return {
                "released": released,
                "orders_expired": 1 if released else 0,
                "orders_preserved_reconciliation": 0,
            }

    fake = Shrinking()
    worker = CleanupWorker(fake, worker_id="w")
    first = await worker.run_once()
    second = await worker.run_once()
    assert first["released"] == 2
    assert second["released"] == 0
    assert len(fake.calls) == 2


def test_cli_defaults():
    args = build_parser().parse_args([])
    assert args.once is False
    assert args.interval_seconds == 60
    assert args.batch_size == DEFAULT_BATCH_SIZE
    assert args.batch_size == 100


def test_cli_once_and_batch_size_flags():
    args = build_parser().parse_args(["--once", "--batch-size", "50"])
    assert args.once is True
    assert args.batch_size == 50
