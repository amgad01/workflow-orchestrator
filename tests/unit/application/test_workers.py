
import pytest

from src.adapters.secondary.workers.external_service_worker import ExternalServiceWorker
from src.adapters.secondary.workers.llm_service_worker import LLMServiceWorker
from src.ports.secondary.message_broker import TaskMessage


@pytest.mark.asyncio
async def test_external_service_worker_success():
    worker = ExternalServiceWorker()
    task = TaskMessage(
        id="task-1",
        execution_id="exec-1",
        node_id="node-1",
        handler="call_external_service",
        config={"url": "http://example.com"}
    )
    
    result = await worker.process(task)
    
    assert result["status_code"] == 200
    assert "url" in result
    assert result["url"] == "http://example.com"

@pytest.mark.asyncio
async def test_external_service_worker_failure():
    worker = ExternalServiceWorker()
    task = TaskMessage(
        id="task-1",
        execution_id="exec-1",
        node_id="node-1",
        handler="call_external_service",
        config={"url": "http://example.com", "simulate_failure": True}
    )
    
    with pytest.raises(Exception) as exc_info:
        await worker.process(task)
    
    assert "Simulated failure" in str(exc_info.value)

@pytest.mark.asyncio
async def test_llm_service_worker_success():
    worker = LLMServiceWorker()
    task = TaskMessage(
        id="task-2",
        execution_id="exec-1",
        node_id="node-2",
        handler="call_llm",
        config={"prompt": "Hello", "model": "gpt-4"}
    )
    
    result = await worker.process(task)
    
    assert "response" in result
    assert result["model"] == "gpt-4"

@pytest.mark.asyncio
async def test_input_worker():
    from src.adapters.secondary.workers.io_workers import InputWorker
    worker = InputWorker()
    task = TaskMessage(
        id="task-3",
        execution_id="exec-1",
        node_id="node-3",
        handler="input",
        config={"key": "val"}
    )
    result = await worker.process(task)
    assert result["initialized"] is True
    assert result["key"] == "val"

@pytest.mark.asyncio
async def test_output_worker():
    from src.adapters.secondary.workers.io_workers import OutputWorker
    worker = OutputWorker()
    task = TaskMessage(
        id="task-4",
        execution_id="exec-1",
        node_id="node-4",
        handler="output",
        config={"final": "data"}
    )
    result = await worker.process(task)
    assert result["aggregated"] is True
    assert result["config"]["final"] == "data"
