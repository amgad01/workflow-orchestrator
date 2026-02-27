from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.application.workflow.use_cases.orchestrate import OrchestrateUseCase
from src.domain.workflow.entities.execution import Execution
from src.domain.workflow.entities.workflow import Workflow
from src.domain.workflow.value_objects.node_status import NodeStatus
from src.ports.secondary.message_broker import CompletionMessage


@pytest.fixture
def mock_workflow_repo():
    return AsyncMock()


@pytest.fixture
def mock_execution_repo():
    return AsyncMock()


@pytest.fixture
def mock_state_store():
    return AsyncMock()


@pytest.fixture
def mock_message_broker():
    return AsyncMock()


@pytest.fixture
def orchestrate_use_case(
    mock_workflow_repo, mock_execution_repo, mock_state_store, mock_message_broker
):
    return OrchestrateUseCase(
        workflow_repository=mock_workflow_repo,
        execution_repository=mock_execution_repo,
        state_store=mock_state_store,
        message_broker=mock_message_broker,
    )


@pytest.mark.asyncio
async def test_handle_completion_success(
    orchestrate_use_case, mock_execution_repo, mock_state_store, mock_workflow_repo
):
    # Setup
    execution_id = "exec-1"
    node_id = "node-1"
    execution = Execution(workflow_id="wf-1", id=execution_id)
    execution.status = NodeStatus.RUNNING
    execution.started_at = datetime.now(timezone.utc)
    execution.timeout_seconds = 100
    mock_execution_repo.get_by_id.return_value = execution
    mock_state_store.get_all_node_statuses.return_value = {node_id: NodeStatus.COMPLETED}

    workflow = Workflow(
        name="test", dag_json={"nodes": [{"id": node_id, "handler": "input"}]}, id="wf-1"
    )
    mock_workflow_repo.get_by_id.return_value = workflow

    completion = CompletionMessage(
        id="msg-1",
        execution_id=execution_id,
        node_id=node_id,
        success=True,
        output={"result": "ok"},
    )

    # Execute
    await orchestrate_use_case.handle_completion(completion)

    # Verify
    mock_state_store.set_node_status.assert_called_with(execution_id, node_id, NodeStatus.COMPLETED)
    mock_state_store.set_node_output.assert_called_with(execution_id, node_id, {"result": "ok"})


@pytest.mark.asyncio
async def test_handle_completion_failure(
    orchestrate_use_case, mock_execution_repo, mock_state_store
):
    # Setup
    execution_id = "exec-1"
    node_id = "node-1"
    execution = Execution(workflow_id="wf-1", id=execution_id)
    execution.status = NodeStatus.RUNNING
    execution.started_at = datetime.now(timezone.utc)
    execution.timeout_seconds = 100
    mock_execution_repo.get_by_id.return_value = execution

    # Configure mock_state_store to return a dict for get_all_node_statuses
    mock_state_store.get_all_node_statuses.return_value = {node_id: NodeStatus.FAILED}

    completion = CompletionMessage(
        id="msg-1",
        execution_id=execution_id,
        node_id=node_id,
        success=False,
        error="Something went wrong",
    )

    # Execute
    await orchestrate_use_case.handle_completion(completion)

    # Verify
    mock_state_store.set_node_status.assert_called_with(execution_id, node_id, NodeStatus.FAILED)
    assert execution.status == NodeStatus.FAILED
    mock_execution_repo.update.assert_called_with(execution)


@pytest.mark.asyncio
async def test_check_all_timeouts(orchestrate_use_case, mock_execution_repo, mock_state_store):
    # Setup
    now = datetime.now(timezone.utc)
    execution = Execution(workflow_id="wf-1", id="exec-1")
    execution.status = NodeStatus.RUNNING
    from datetime import timedelta

    execution.started_at = now - timedelta(seconds=10)
    execution.timeout_seconds = 5

    mock_execution_repo.get_running_executions.return_value = [execution]
    mock_state_store.get_all_node_statuses.return_value = {"n1": NodeStatus.RUNNING}

    # Execute
    await orchestrate_use_case.check_all_timeouts()

    # Verify
    assert execution.status == NodeStatus.FAILED
    mock_execution_repo.update.assert_called_with(execution)


@pytest.mark.asyncio
async def test_check_all_timeouts_no_timeout(orchestrate_use_case, mock_execution_repo):
    # Setup
    now = datetime.now(timezone.utc)
    execution = Execution(workflow_id="wf-1", id="exec-1")
    execution.status = NodeStatus.RUNNING
    execution.started_at = (
        now.replace(second=now.second - 2)
        if now.second >= 2
        else now.replace(minute=now.minute - 1, second=58)
    )
    execution.timeout_seconds = 5

    mock_execution_repo.get_running_executions.return_value = [execution]

    # Execute
    await orchestrate_use_case.check_all_timeouts()

    # Verify
    assert execution.status == NodeStatus.RUNNING
    mock_execution_repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_dag_cache_is_bounded():
    """Verify the DAG cache uses TTLCache and has bounded size."""
    from cachetools import TTLCache

    cache = OrchestrateUseCase._dag_cache
    assert isinstance(cache, TTLCache), "DAG cache should be a TTLCache instance"
    assert cache.maxsize > 0, "DAG cache max size should be positive"


@pytest.mark.asyncio
async def test_dag_cache_evicts_on_overflow(
    mock_workflow_repo, mock_execution_repo, mock_state_store, mock_message_broker
):
    """Verify the DAG cache evicts entries when maxsize is exceeded."""
    from cachetools import TTLCache

    # Create a small cache for testing
    original_cache = OrchestrateUseCase._dag_cache
    OrchestrateUseCase._dag_cache = TTLCache(maxsize=2, ttl=60)

    try:
        use_case = OrchestrateUseCase(
            workflow_repository=mock_workflow_repo,
            execution_repository=mock_execution_repo,
            state_store=mock_state_store,
            message_broker=mock_message_broker,
        )

        # Create 3 mock workflows to exceed cache size of 2
        for i in range(3):
            wf = Workflow(
                name=f"test-{i}",
                dag_json={"nodes": [{"id": f"n{i}", "handler": "input"}]},
                id=f"wf-{i}",
            )
            mock_workflow_repo.get_by_id.return_value = wf
            await use_case._get_workflow_dag(f"wf-{i}")

        # Cache should only hold 2 entries (maxsize=2), first one evicted
        assert len(OrchestrateUseCase._dag_cache) == 2
        assert "wf-0" not in OrchestrateUseCase._dag_cache
    finally:
        OrchestrateUseCase._dag_cache = original_cache
