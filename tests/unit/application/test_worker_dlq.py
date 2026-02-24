from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry
from src.ports.secondary.message_broker import TaskMessage
from src.worker import WorkerRunner


class TestWorkerDLQIntegration:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.sismember.return_value = False
        redis.sadd.return_value = True
        redis.expire.return_value = True
        redis.incr.return_value = 1
        return redis

    @pytest.fixture
    def mock_broker(self):
        broker = AsyncMock()
        broker.publish_completion.return_value = None
        broker.acknowledge_task.return_value = None
        return broker

    @pytest.fixture
    def mock_dlq_repository(self):
        dlq = AsyncMock()
        dlq.push.return_value = None
        return dlq

    @pytest.fixture
    def task_message(self):
        return TaskMessage(
            id="task-123",
            execution_id="exec-456",
            node_id="node-a",
            handler="call_llm",
            config={"prompt": "test"},
            stream_id="stream-789",
        )

    @pytest.mark.asyncio
    async def test_task_moves_to_dlq_after_max_retries(
        self, mock_redis, mock_broker, mock_dlq_repository, task_message
    ):
        with (
            patch("src.worker.redis_client", mock_redis),
            patch("src.worker.settings") as mock_settings,
        ):
            mock_settings.DLQ_ENABLED = True
            mock_settings.DLQ_MAX_RETRIES = 3
            mock_settings.WORKER_ENABLE_DELAYS = False
            mock_settings.WORKER_BACKOFF_BASE_SECONDS = 1.0
            mock_settings.WORKER_BACKOFF_MAX_SECONDS = 30.0
            mock_settings.WORKER_BACKOFF_JITTER_MAX = 0.1
            mock_settings.WORKER_ERROR_PAUSE_SECONDS = 0.0

            # Simulate 3rd retry
            mock_redis.incr.return_value = 3

            runner = WorkerRunner()
            runner._broker = mock_broker
            runner._dlq_repository = mock_dlq_repository

            # Register a failing handler
            class FailingHandler:
                handler_name = "call_llm"

                async def process(self, task):
                    raise Exception("Simulated failure")

            runner._handlers["call_llm"] = FailingHandler()

            await runner.process_task(task_message)

            # Should have pushed to DLQ
            mock_dlq_repository.push.assert_called_once()
            call_args = mock_dlq_repository.push.call_args[0][0]
            assert isinstance(call_args, DeadLetterEntry)
            assert call_args.task_id == task_message.id

    @pytest.mark.asyncio
    async def test_task_not_moved_to_dlq_before_max_retries(
        self, mock_redis, mock_broker, mock_dlq_repository, task_message
    ):
        with (
            patch("src.worker.redis_client", mock_redis),
            patch("src.worker.settings") as mock_settings,
        ):
            mock_settings.DLQ_ENABLED = True
            mock_settings.DLQ_MAX_RETRIES = 3
            mock_settings.WORKER_ENABLE_DELAYS = False
            mock_settings.WORKER_BACKOFF_BASE_SECONDS = 1.0
            mock_settings.WORKER_BACKOFF_MAX_SECONDS = 30.0
            mock_settings.WORKER_BACKOFF_JITTER_MAX = 0.1
            mock_settings.WORKER_ERROR_PAUSE_SECONDS = 0.0

            # First retry
            mock_redis.incr.return_value = 1

            runner = WorkerRunner()
            runner._broker = mock_broker
            runner._dlq_repository = mock_dlq_repository

            class FailingHandler:
                handler_name = "call_llm"

                async def process(self, task):
                    raise Exception("Simulated failure")

            runner._handlers["call_llm"] = FailingHandler()

            await runner.process_task(task_message)

            # Should NOT have pushed to DLQ yet
            mock_dlq_repository.push.assert_not_called()

    @pytest.mark.asyncio
    async def test_dlq_disabled_skips_tracking(
        self, mock_redis, mock_broker, mock_dlq_repository, task_message
    ):
        with (
            patch("src.worker.redis_client", mock_redis),
            patch("src.worker.settings") as mock_settings,
        ):
            mock_settings.DLQ_ENABLED = False
            mock_settings.WORKER_ENABLE_DELAYS = False

            runner = WorkerRunner()
            runner._broker = mock_broker
            runner._dlq_repository = mock_dlq_repository

            class FailingHandler:
                handler_name = "call_llm"

                async def process(self, task):
                    raise Exception("Simulated failure")

            runner._handlers["call_llm"] = FailingHandler()

            await runner.process_task(task_message)

            # Should not increment retry counter
            mock_redis.incr.assert_not_called()
            mock_dlq_repository.push.assert_not_called()


class TestDeadLetterEntryValidation:
    def test_entry_generates_unique_id(self):
        entry1 = DeadLetterEntry(
            task_id="task-1",
            execution_id="exec-1",
            node_id="node-a",
            handler="handler",
            config={},
            error_message="error",
            retry_count=3,
            original_timestamp=datetime.now(timezone.utc),
        )
        entry2 = DeadLetterEntry(
            task_id="task-1",
            execution_id="exec-1",
            node_id="node-a",
            handler="handler",
            config={},
            error_message="error",
            retry_count=3,
            original_timestamp=datetime.now(timezone.utc),
        )

        assert entry1.id != entry2.id

    def test_entry_serialization_roundtrip(self):
        original = DeadLetterEntry(
            id="fixed-id",
            task_id="task-123",
            execution_id="exec-456",
            node_id="node-a",
            handler="call_llm",
            config={"prompt": "test", "nested": {"key": "value"}},
            error_message="Connection timeout",
            retry_count=3,
            original_timestamp=datetime(2025, 1, 29, 12, 0, 0),
            failed_at=datetime(2025, 1, 29, 12, 1, 0),
        )

        data = original.to_dict()
        restored = DeadLetterEntry.from_dict(data)

        assert restored.id == original.id
        assert restored.task_id == original.task_id
        assert restored.config == original.config
        assert restored.retry_count == original.retry_count

    def test_entry_handles_empty_config(self):
        entry = DeadLetterEntry(
            task_id="task-1",
            execution_id="exec-1",
            node_id="node-a",
            handler="handler",
            config={},
            error_message="error",
            retry_count=0,
            original_timestamp=datetime.now(timezone.utc),
        )

        data = entry.to_dict()
        assert data["config"] == {}
