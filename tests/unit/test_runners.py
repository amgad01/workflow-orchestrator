import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from src.worker import WorkerRunner
from src.orchestrator import OrchestratorRunner
from src.ports.secondary.message_broker import CompletionMessage, TaskMessage
from src.domain.workflow.value_objects.node_status import NodeStatus

@pytest.mark.asyncio
async def test_worker_runner_process_task():
    with patch("src.worker.uuid4", return_value=MagicMock(hex="test-hex")), \
         patch("src.worker.RedisMessageBroker") as mock_broker_cls, \
         patch("src.worker.RedisStateStore"), \
         patch("src.worker.redis_client") as mock_redis:
             
        mock_broker = mock_broker_cls.return_value
        mock_broker.acknowledge_task = AsyncMock()
        mock_broker.publish_completion = AsyncMock()
        
        runner = WorkerRunner()
        
        # Mock handler
        mock_handler = AsyncMock()
        mock_handler.handler_name = "test_h"
        mock_handler.process.return_value = {"result": "ok"}
        runner.register_handler(mock_handler)
        
        task = TaskMessage(
            id="t1", execution_id="e1", node_id="n1", 
            handler="test_h", config={}
        )
        
        # Mock idempotency check: not processed
        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.sadd = AsyncMock()
        mock_redis.expire = AsyncMock()

        await runner.process_task(task)
        
        mock_handler.process.assert_called_once_with(task)
        assert mock_broker.publish_completion.called

@pytest.mark.asyncio
async def test_orchestrator_runner_handle_completion():
    with patch("src.orchestrator.uuid4", return_value=MagicMock(hex="test-hex")), \
         patch("src.orchestrator.RedisMessageBroker"), \
         patch("src.orchestrator.RedisStateStore"), \
         patch("src.orchestrator.async_session_factory"), \
         patch("src.orchestrator.OrchestrateUseCase") as mock_use_case_cls:
             
        runner = OrchestratorRunner()
        completion = CompletionMessage(
            id="m1", execution_id="e1", node_id="n1", success=True
        )
        
        mock_use_case_instance = mock_use_case_cls.return_value
        mock_use_case_instance.handle_completion = AsyncMock()
        
        await runner.handle_completion(completion)
        
        assert mock_use_case_cls.called
        assert mock_use_case_instance.handle_completion.called

@pytest.mark.asyncio
async def test_orchestrator_runner_run_loop():
    with patch("src.orchestrator.RedisMessageBroker") as mock_broker_cls, \
         patch("src.orchestrator.RedisStateStore"), \
         patch("src.orchestrator.async_session_factory"), \
         patch("src.orchestrator.OrchestrateUseCase") as mock_use_case_cls:
             
        mock_broker = mock_broker_cls.return_value
        mock_broker.consume_completions = AsyncMock(side_effect=[
            [CompletionMessage(id="m1", execution_id="e1", node_id="n1", success=True)],
            KeyboardInterrupt()
        ])
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
    with patch("src.worker.RedisMessageBroker") as mock_broker_cls, \
         patch("src.worker.RedisStateStore"), \
         patch("src.worker.redis_client"), \
         patch("src.worker.WorkerRunner.process_task") as mock_process:
             
        mock_broker = mock_broker_cls.return_value
        mock_broker.consume_tasks = AsyncMock(side_effect=[
            [TaskMessage(id="t1", execution_id="e1", node_id="n1", handler="h", config={})],
            KeyboardInterrupt()
        ])
        mock_broker.create_consumer_groups = AsyncMock()
        
        runner = WorkerRunner()
        try:
            await runner.run()
        except KeyboardInterrupt:
            pass
        
        assert mock_broker.create_consumer_groups.called
        assert mock_process.called
