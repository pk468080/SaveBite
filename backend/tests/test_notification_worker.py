"""W7 worker tests: pass order, stats merge, failure handling,
and shutdown. The database functions themselves are SQL
(see the migration-consistency tests); these tests cover
only the Python driver logic, with a fake RPC client."""

import asyncio

import pytest

from app.notification_worker import Worker


class FakeRpc:
    def __init__(self, enqueued=3, stats=None, fail_on=None):
        self.calls = []
        self.enqueued = enqueued
        self.stats = stats or {
            "processed": 2,
            "delivered": 2,
            "skipped": 0,
            "retried": 0,
            "dead": 0,
        }
        self.fail_on = fail_on or set()

    async def rpc(self, name, params):
        self.calls.append((name, params))
        if name in self.fail_on:
            raise RuntimeError("upstream down")
        if name == "backend_enqueue_pickup_reminders":
            return self.enqueued
        return dict(self.stats)


@pytest.mark.asyncio
async def test_run_once_enqueues_before_processing_and_merges_stats():
    fake = FakeRpc()
    worker = Worker(fake, worker_id="test-worker", batch_size=10, window_minutes=60)
    result = await worker.run_once()
    # Reminders first, then one processor batch — never the reverse.
    assert [name for name, _ in fake.calls] == [
        "backend_enqueue_pickup_reminders",
        "backend_process_notification_outbox",
    ]
    assert fake.calls[0][1]["p_window_minutes"] == 60
    assert "p_now" in fake.calls[0][1]
    assert fake.calls[1][1] == {"p_worker_id": "test-worker", "p_batch_size": 10}
    assert result["reminders_enqueued"] == 3
    assert result["delivered"] == 2


@pytest.mark.asyncio
async def test_run_once_propagates_rpc_failure():
    fake = FakeRpc(fail_on={"backend_process_notification_outbox"})
    worker = Worker(fake, worker_id="w")
    with pytest.raises(RuntimeError):
        await worker.run_once()


@pytest.mark.asyncio
async def test_run_forever_stops_immediately_when_flag_set():
    fake = FakeRpc()
    worker = Worker(fake, worker_id="w")
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
            self.process_calls = 0

        async def rpc(self, name, params):
            self.calls.append((name, params))
            if name == "backend_process_notification_outbox":
                self.process_calls += 1
                if self.process_calls == 1:
                    raise RuntimeError("boom")
                self.stop.set()
                return dict(self.stats)
            return self.enqueued

    stop = asyncio.Event()
    fake = Flaky(stop)
    worker = Worker(fake, worker_id="w")
    await asyncio.wait_for(worker.run_forever(0, stop), timeout=5)
    assert fake.process_calls == 2
