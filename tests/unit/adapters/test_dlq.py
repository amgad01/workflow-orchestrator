import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.adapters.secondary.redis.redis_dlq_repository import RedisDLQRepository
from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry


class TestRedisDLQRepository:
    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.fixture
    def dlq_repository(self, mock_redis):
        return RedisDLQRepository(mock_redis)

    @pytest.fixture
    def sample_entry(self):
        return DeadLetterEntry(
            id="entry-123",
            task_id="task-456",
            execution_id="exec-789",
            node_id="node-a",
            handler="call_llm",
            config={"prompt": "test"},
            error_message="Connection timeout",
            retry_count=3,
            original_timestamp=datetime(2025, 1, 29, 12, 0, 0),
            failed_at=datetime(2025, 1, 29, 12, 1, 0),
        )

    @pytest.mark.asyncio
    async def test_push_adds_entry_to_stream(self, dlq_repository, mock_redis, sample_entry):
        await dlq_repository.push(sample_entry)

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == RedisDLQRepository.DLQ_STREAM
        assert call_args[0][1]["id"] == sample_entry.id

    @pytest.mark.asyncio
    async def test_list_entries_returns_parsed_entries(
        self, dlq_repository, mock_redis, sample_entry
    ):
        mock_redis.xrange.return_value = [
            ("stream-id-1", {"id": sample_entry.id, "data": json.dumps(sample_entry.to_dict())}),
        ]

        entries = await dlq_repository.list_entries(limit=10)

        assert len(entries) == 1
        assert entries[0].id == sample_entry.id
        assert entries[0].task_id == sample_entry.task_id

    @pytest.mark.asyncio
    async def test_count_returns_stream_length(self, dlq_repository, mock_redis):
        mock_redis.xlen.return_value = 42

        count = await dlq_repository.count()

        assert count == 42

    @pytest.mark.asyncio
    async def test_delete_removes_entry(self, dlq_repository, mock_redis, sample_entry):
        mock_redis.xrange.return_value = [
            ("stream-id-1", {"id": sample_entry.id, "data": json.dumps(sample_entry.to_dict())}),
        ]

        deleted = await dlq_repository.delete(sample_entry.id)

        assert deleted is True
        mock_redis.xdel.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, dlq_repository, mock_redis):
        mock_redis.xrange.return_value = []

        deleted = await dlq_repository.delete("nonexistent-id")

        assert deleted is False


class TestDeadLetterEntry:
    def test_to_dict_serialization(self):
        entry = DeadLetterEntry(
            id="entry-123",
            task_id="task-456",
            execution_id="exec-789",
            node_id="node-a",
            handler="call_llm",
            config={"prompt": "test"},
            error_message="Connection timeout",
            retry_count=3,
            original_timestamp=datetime(2025, 1, 29, 12, 0, 0),
            failed_at=datetime(2025, 1, 29, 12, 1, 0),
        )

        data = entry.to_dict()

        assert data["id"] == "entry-123"
        assert data["task_id"] == "task-456"
        assert data["retry_count"] == 3
        assert "2025-01-29" in data["original_timestamp"]

    def test_from_dict_deserialization(self):
        data = {
            "id": "entry-123",
            "task_id": "task-456",
            "execution_id": "exec-789",
            "node_id": "node-a",
            "handler": "call_llm",
            "config": {"prompt": "test"},
            "error_message": "Connection timeout",
            "retry_count": 3,
            "original_timestamp": "2025-01-29T12:00:00",
            "failed_at": "2025-01-29T12:01:00",
        }

        entry = DeadLetterEntry.from_dict(data)

        assert entry.id == "entry-123"
        assert entry.task_id == "task-456"
        assert entry.retry_count == 3
        assert entry.original_timestamp == datetime(2025, 1, 29, 12, 0, 0)
