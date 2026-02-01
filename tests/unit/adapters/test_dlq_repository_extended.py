import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from src.adapters.secondary.redis.redis_dlq_repository import RedisDLQRepository
from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry
import json


class TestRedisDLQRepositoryExtended:
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
            config={"prompt": "test", "model": "gpt-4"},
            error_message="Connection timeout after 30s",
            retry_count=3,
            original_timestamp=datetime(2025, 1, 29, 12, 0, 0),
            failed_at=datetime(2025, 1, 29, 12, 1, 0),
        )

    @pytest.mark.asyncio
    async def test_push_entry_stores_correct_data(self, dlq_repository, mock_redis, sample_entry):
        await dlq_repository.push(sample_entry)
        
        # Verify xadd was called with correct stream
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == "workflow:dlq"
        
        # Verify the data contains entry id
        data = call_args[0][1]
        assert data["id"] == sample_entry.id
        
        # Verify index is updated
        mock_redis.hset.assert_called_with("workflow:dlq:index", sample_entry.id, "1")

    @pytest.mark.asyncio
    async def test_pop_entry_removes_from_dlq(self, dlq_repository, mock_redis, sample_entry):
        # Setup mock to return the entry
        mock_redis.xrange.return_value = [
            ("stream-id-1", {"id": sample_entry.id, "data": json.dumps(sample_entry.to_dict())}),
        ]
        mock_redis.xdel.return_value = 1
        mock_redis.hdel.return_value = 1
        
        result = await dlq_repository.pop(sample_entry.id)
        
        assert result is not None
        assert result.id == sample_entry.id
        mock_redis.xdel.assert_called()
        mock_redis.hdel.assert_called()

    @pytest.mark.asyncio
    async def test_pop_nonexistent_returns_none(self, dlq_repository, mock_redis):
        mock_redis.xrange.return_value = []
        
        result = await dlq_repository.pop("nonexistent-id")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_list_entries_handles_corrupted_data(self, dlq_repository, mock_redis):
        mock_redis.xrange.return_value = [
            ("stream-1", {"id": "valid", "data": json.dumps({"id": "valid", "task_id": "t1", "execution_id": "e1", "node_id": "n1", "handler": "h1", "config": {}, "error_message": "err", "retry_count": 1, "original_timestamp": "2025-01-29T12:00:00", "failed_at": "2025-01-29T12:00:00"})}),
            ("stream-2", {"id": "corrupted", "data": "not valid json"}),
            ("stream-3", {"id": "missing", "data": "{}"}),  # Missing required fields
        ]
        
        entries = await dlq_repository.list_entries(limit=10)
        
        # Only valid entry should be returned
        assert len(entries) == 1
        assert entries[0].id == "valid"

    @pytest.mark.asyncio
    async def test_count_returns_stream_length(self, dlq_repository, mock_redis):
        mock_redis.xlen.return_value = 42
        
        count = await dlq_repository.count()
        
        assert count == 42
        mock_redis.xlen.assert_called_with("workflow:dlq")

    @pytest.mark.asyncio
    async def test_delete_finds_and_removes_entry(self, dlq_repository, mock_redis, sample_entry):
        mock_redis.xrange.return_value = [
            ("stream-id-1", {"id": "other-id", "data": "..."}),
            ("stream-id-2", {"id": sample_entry.id, "data": "..."}),
        ]
        mock_redis.xdel.return_value = 1
        mock_redis.hdel.return_value = 1
        
        result = await dlq_repository.delete(sample_entry.id)
        
        assert result is True
        mock_redis.xdel.assert_called_with("workflow:dlq", "stream-id-2")
        mock_redis.hdel.assert_called_with("workflow:dlq:index", sample_entry.id)

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, dlq_repository, mock_redis):
        mock_redis.xrange.return_value = [
            ("stream-id-1", {"id": "other-id", "data": "..."}),
        ]
        
        result = await dlq_repository.delete("nonexistent-id")
        
        assert result is False
        mock_redis.xdel.assert_not_called()


class TestDeadLetterEntryEdgeCases:
    def test_entry_with_complex_config(self):
        entry = DeadLetterEntry(
            task_id="task-1",
            execution_id="exec-1",
            node_id="node-a",
            handler="handler",
            config={
                "nested": {"key": "value", "list": [1, 2, 3]},
                "array": ["a", "b", "c"],
                "number": 42,
                "boolean": True,
            },
            error_message="error",
            retry_count=1,
            original_timestamp=datetime.now(timezone.utc),
        )
        
        data = entry.to_dict()
        restored = DeadLetterEntry.from_dict(data)
        
        assert restored.config == entry.config
        assert restored.config["nested"]["list"] == [1, 2, 3]

    def test_entry_with_long_error_message(self):
        long_error = "Error: " + "x" * 10000
        
        entry = DeadLetterEntry(
            task_id="task-1",
            execution_id="exec-1",
            node_id="node-a",
            handler="handler",
            config={},
            error_message=long_error,
            retry_count=1,
            original_timestamp=datetime.now(timezone.utc),
        )
        
        data = entry.to_dict()
        restored = DeadLetterEntry.from_dict(data)
        
        assert restored.error_message == long_error

    def test_entry_with_zero_retry_count(self):
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
        
        assert entry.retry_count == 0
