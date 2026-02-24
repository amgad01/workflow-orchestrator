from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.secondary.workers.decision_worker import DecisionWorker
from src.adapters.secondary.workers.reaper import ReaperRunner
from src.ports.secondary.message_broker import TaskMessage


class TestDecisionWorker:
    @pytest.fixture
    def worker(self):
        return DecisionWorker()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value_a, operator, value_b, expected", [
        ("test", "==", "test", True),
        ("test ", "==", " test", True),
        ("test", "==", "other", False),
        ("test", "!=", "other", True),
        ("test", "!=", "test", False),
        (10, ">", 5, True),
        (5, ">", 10, False),
        (10, "<", 20, True),
        (20, "<", 10, False),
        (10, ">=", 10, True),
        (10, ">=", 5, True),
        (5, ">=", 10, False),
        (10, "<=", 10, True),
        (10, "<=", 20, True),
        (20, "<=", 10, False),
        ("invalid", ">", 10, False), # Should handle float conversion failure
    ])
    async def test_decision_logic(self, worker, value_a, operator, value_b, expected):
        task = TaskMessage(
            id="t1",
            execution_id="e1",
            node_id="n1",
            handler="decision",
            config={"value_a": value_a, "operator": operator, "value_b": value_b}
        )
        
        result = await worker.process(task)
        assert result["result"] == expected


class TestReaperRunner:
    @pytest.fixture
    def mock_broker(self):
        broker = AsyncMock()
        broker.create_consumer_groups.return_value = None
        broker.claim_stalled_tasks.return_value = []
        broker.publish_task.return_value = None
        broker.acknowledge_task.return_value = None
        return broker

    @pytest.mark.asyncio
    async def test_reaper_claims_and_resurrects_tasks(self, mock_broker):
        mock_event = MagicMock()
        # Need enough Falses for while loop, inner task loop, and wait check
        mock_event.is_set.side_effect = [False, False, False, True] 
        mock_event.wait = AsyncMock()
        
        with patch("src.adapters.secondary.workers.reaper.RedisMessageBroker", return_value=mock_broker), \
             patch("src.adapters.secondary.workers.reaper.redis_client", AsyncMock()), \
             patch("asyncio.Event", return_value=mock_event):
            
            reaper = ReaperRunner(check_interval_seconds=0.1, min_idle_seconds=10)
            
            # Setup mock to return a task
            task = TaskMessage(id="t1", execution_id="e1", node_id="n1", handler="h1", config={})
            mock_broker.claim_stalled_tasks.return_value = [("stream-1", task)]
            
            await reaper.run()
            
            # Verify side effects
            mock_broker.publish_task.assert_called_once_with(task)
            mock_broker.acknowledge_task.assert_called_once_with("stream-1")
            
    @pytest.mark.asyncio
    async def test_reaper_initialization(self):
         with patch("src.adapters.secondary.workers.reaper.redis_client", AsyncMock()):
            reaper = ReaperRunner(check_interval_seconds=10, min_idle_seconds=60)
            assert reaper._check_interval == 10
            assert reaper._min_idle_ms == 60000

class TestDecisionWorkerEdgeCases:
    @pytest.mark.asyncio
    async def test_default_operator(self):
        worker = DecisionWorker()
        task = TaskMessage(
            id="t1", execution_id="e1", node_id="n1", handler="decision",
            config={"value_a": "test", "value_b": "test"}
        )
        result = await worker.process(task)
        assert result["result"] is True # Default is ==

    @pytest.mark.asyncio
    async def test_missing_values(self):
        worker = DecisionWorker()
        task = TaskMessage(
            id="t1", execution_id="e1", node_id="n1", handler="decision",
            config={"operator": "=="} # missing a and b
        )
        result = await worker.process(task)
        assert result["result"] is True # str(None) == str(None) -> "None" == "None"
