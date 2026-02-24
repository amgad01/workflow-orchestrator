from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.workflow.use_cases.cancel_workflow import CancelWorkflowUseCase
from src.application.workflow.use_cases.get_workflow_results import GetWorkflowResultsUseCase
from src.application.workflow.use_cases.get_workflow_status import GetWorkflowStatusUseCase
from src.application.workflow.use_cases.trigger_execution import TriggerExecutionUseCase
from src.domain.workflow.entities.execution import Execution
from src.domain.workflow.entities.workflow import Workflow
from src.domain.workflow.value_objects.node_status import NodeStatus


@pytest.fixture
def mock_repos():
    return {
        "workflow": AsyncMock(),
        "execution": AsyncMock(),
        "state": AsyncMock(),
        "broker": AsyncMock(),
    }


@pytest.mark.asyncio
async def test_trigger_execution_success(mock_repos):
    use_case = TriggerExecutionUseCase(
        mock_repos["workflow"], mock_repos["execution"], mock_repos["state"], mock_repos["broker"]
    )

    execution_id = "exec-1"
    execution = MagicMock(spec=Execution)
    execution.id = execution_id
    execution.status = NodeStatus.PENDING
    execution.workflow_id = "wf-1"
    mock_repos["execution"].get_by_id.return_value = execution

    workflow = MagicMock(spec=Workflow)
    workflow.dag_json = {"nodes": [{"id": "n1", "handler": "h1", "dependencies": []}]}
    mock_repos["workflow"].get_by_id.return_value = workflow
    mock_repos["state"].get_all_node_statuses.return_value = {"n1": NodeStatus.PENDING}

    # Pass execution_id and params (workflow_id is now looked up internally)
    await use_case.execute(execution_id, {})

    # Should have dispatched n1
    mock_repos["broker"].publish_task.assert_called()


@pytest.mark.asyncio
async def test_cancel_workflow_success(mock_repos):
    use_case = CancelWorkflowUseCase(mock_repos["execution"], mock_repos["state"])

    execution_id = "exec-1"
    execution = Execution(workflow_id="wf-1", id=execution_id)
    execution.status = NodeStatus.RUNNING
    execution.initialize_nodes(["n1"])
    execution.node_states["n1"].status = NodeStatus.RUNNING

    mock_repos["execution"].get_by_id.return_value = execution
    mock_repos["state"].get_all_node_statuses.return_value = {"n1": NodeStatus.RUNNING}

    await use_case.execute(execution_id)

    assert execution.status == NodeStatus.CANCELLED
    assert execution.node_states["n1"].status == NodeStatus.CANCELLED
    mock_repos["execution"].update.assert_called_with(execution)
    mock_repos["state"].set_node_status.assert_called_with(execution_id, "n1", NodeStatus.CANCELLED)


@pytest.mark.asyncio
async def test_get_workflow_status(mock_repos):
    use_case = GetWorkflowStatusUseCase(mock_repos["execution"], mock_repos["state"])

    execution_id = "exec-1"
    execution = MagicMock(spec=Execution)
    execution.status = NodeStatus.RUNNING
    execution.workflow_id = "wf-1"
    mock_repos["execution"].get_by_id.return_value = execution
    mock_repos["state"].get_all_node_statuses.return_value = {"n1": NodeStatus.RUNNING}
    # Simulate cache miss to force DB lookup logic
    mock_repos["state"].get_execution_status.return_value = None
    mock_repos["state"].get_execution_metadata.return_value = None

    status = await use_case.execute(execution_id)

    assert status["status"] == "RUNNING"
    assert status["node_statuses"]["n1"] == "RUNNING"


@pytest.mark.asyncio
async def test_get_workflow_results(mock_repos):
    use_case = GetWorkflowResultsUseCase(mock_repos["execution"], mock_repos["state"])

    execution_id = "exec-1"
    execution = MagicMock(spec=Execution)
    execution.status = NodeStatus.COMPLETED
    execution.workflow_id = "wf-1"
    mock_repos["execution"].get_by_id.return_value = execution
    mock_repos["state"].get_all_outputs.return_value = {"n1": {"data": "info"}}

    results = await use_case.execute(execution_id)

    assert results["outputs"]["n1"]["data"] == "info"
