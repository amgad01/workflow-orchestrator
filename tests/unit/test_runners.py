import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator import OrchestratorRunner
from src.ports.secondary.message_broker import CompletionMessage, TaskMessage
from src.worker import WorkerRunner


@pytest.mark.asyncio
async def test_worker_runner_process_task():
    with (
        patch("src.worker.uuid4", return_value=MagicMock(hex="test-hex")),
        patch("src.worker.RedisMessageBroker") as mock_broker_cls,
        patch("src.worker.RedisStateStore"),
        patch("src.worker.redis_client") as mock_redis,
    ):
        mock_broker = mock_broker_cls.return_value
        mock_broker.acknowledge_task = AsyncMock()
        mock_broker.publish_completion = AsyncMock()

        runner = WorkerRunner()

        # Mock handler
        mock_handler = AsyncMock()
        mock_handler.handler_name = "test_h"
        mock_handler.process.return_value = {"result": "ok"}
        runner.register_handler(mock_handler)

        task = TaskMessage(id="t1", execution_id="e1", node_id="n1", handler="test_h", config={})

        # Mock idempotency check: not processed
        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.sadd = AsyncMock()
        mock_redis.expire = AsyncMock()

        await runner.process_task(task)

        mock_handler.process.assert_called_once_with(task)
        assert mock_broker.publish_completion.called


@pytest.mark.asyncio
async def test_orchestrator_runner_handle_completion():
    with (
        patch("src.orchestrator.uuid4", return_value=MagicMock(hex="test-hex")),
        patch("src.orchestrator.RedisMessageBroker"),
        patch("src.orchestrator.RedisStateStore"),
        patch("src.orchestrator.async_session_factory"),
        patch("src.orchestrator.OrchestrateUseCase") as mock_use_case_cls,
    ):
        runner = OrchestratorRunner()
        completion = CompletionMessage(id="m1", execution_id="e1", node_id="n1", success=True)

        mock_use_case_instance = mock_use_case_cls.return_value
        mock_use_case_instance.handle_completion = AsyncMock()

        await runner.handle_completion(completion)

        assert mock_use_case_cls.called
        assert mock_use_case_instance.handle_completion.called


@pytest.mark.asyncio
async def test_orchestrator_runner_run_loop():
    with (
        patch("src.orchestrator.RedisMessageBroker") as mock_broker_cls,
        patch("src.orchestrator.RedisStateStore"),
        patch("src.orchestrator.async_session_factory"),
        patch("src.orchestrator.OrchestrateUseCase") as mock_use_case_cls,
    ):
        mock_broker = mock_broker_cls.return_value
        mock_broker.consume_completions = AsyncMock(
            side_effect=[
                [CompletionMessage(id="m1", execution_id="e1", node_id="n1", success=True)],
                KeyboardInterrupt(),
            ]
        )
        mock_broker.create_consumer_groups = AsyncMock()

        runner = OrchestratorRunner()
        try:
            await runner.run()
        except KeyboardInterrupt:
            pass

        assert mock_broker.create_consumer_groups.called
        assert mock_use_case_cls.called


@pytest.mark.asyncio
async def test_worker_runner_run_loop():
    with (
        patch("src.worker.RedisMessageBroker") as mock_broker_cls,
        patch("src.worker.RedisStateStore"),
        patch("src.worker.redis_client"),
        patch("src.worker.WorkerRunner.process_task") as mock_process,
    ):
        mock_broker = mock_broker_cls.return_value
        mock_broker.consume_tasks = AsyncMock(
            side_effect=[
                [TaskMessage(id="t1", execution_id="e1", node_id="n1", handler="h", config={})],
                KeyboardInterrupt(),
            ]
        )
        mock_broker.create_consumer_groups = AsyncMock()

        runner = WorkerRunner()
        try:
            await runner.run()
        except KeyboardInterrupt:
            pass

        assert mock_broker.create_consumer_groups.called
        assert mock_process.called


@pytest.mark.asyncio
async def test_worker_graceful_shutdown_drains_in_flight():
    """Verify the worker waits for in-flight tasks during shutdown."""
    with (
        patch("src.worker.RedisMessageBroker") as mock_broker_cls,
        patch("src.worker.RedisStateStore"),
        patch("src.worker.redis_client"),
        patch("src.worker.RedisDLQRepository"),
    ):
        mock_broker = mock_broker_cls.return_value
        mock_broker.create_consumer_groups = AsyncMock()
        mock_broker.publish_completion = AsyncMock()
        mock_broker.acknowledge_task = AsyncMock()

        runner = WorkerRunner()

        # Create a fake slow task
        slow_task = asyncio.create_task(asyncio.sleep(0.1))
        runner._in_flight.add(slow_task)
        slow_task.add_done_callback(runner._in_flight.discard)

        # Drain should wait for the task to finish
        await runner._drain_in_flight()
        assert len(runner._in_flight) == 0


@pytest.mark.asyncio
async def test_worker_drain_cancels_after_timeout():
    """Verify the worker cancels tasks that exceed the shutdown timeout."""
    with (
        patch("src.worker.RedisMessageBroker"),
        patch("src.worker.RedisStateStore"),
        patch("src.worker.redis_client"),
        patch("src.worker.RedisDLQRepository"),
    ):
        runner = WorkerRunner()
        runner.SHUTDOWN_TIMEOUT_SECONDS = 0.1  # Very short timeout

        # Create a task that would take forever
        stuck_task = asyncio.create_task(asyncio.sleep(999))
        runner._in_flight.add(stuck_task)
        stuck_task.add_done_callback(runner._in_flight.discard)

        await runner._drain_in_flight()
        assert stuck_task.cancelled()


@pytest.mark.asyncio
async def test_orchestrator_graceful_shutdown_drains():
    """Verify the orchestrator drains in-flight completions during shutdown."""
    with (
        patch("src.orchestrator.RedisMessageBroker"),
        patch("src.orchestrator.RedisStateStore"),
    ):
        runner = OrchestratorRunner()

        fast_task = asyncio.create_task(asyncio.sleep(0.05))
        runner._in_flight.add(fast_task)
        fast_task.add_done_callback(runner._in_flight.discard)

        await runner._drain_in_flight()
        assert len(runner._in_flight) == 0


@pytest.mark.asyncio
async def test_worker_has_shutdown_event():
    """Verify the worker exposes a shutdown_event for clean signal handling."""
    with (
        patch("src.worker.RedisMessageBroker"),
        patch("src.worker.RedisStateStore"),
        patch("src.worker.redis_client"),
        patch("src.worker.RedisDLQRepository"),
    ):
        runner = WorkerRunner()
        assert hasattr(runner, "_shutdown_event")
        assert isinstance(runner._shutdown_event, asyncio.Event)
        assert not runner._shutdown_event.is_set()
