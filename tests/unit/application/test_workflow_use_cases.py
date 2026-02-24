from unittest.mock import AsyncMock

import pytest


class TestSubmitWorkflow:
    @pytest.fixture
    def mock_workflow_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_execution_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_state_store(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_submit_workflow_creates_entities(
        self, mock_workflow_repo, mock_execution_repo, mock_state_store
    ):
        from src.application.workflow.use_cases.submit_workflow import SubmitWorkflowUseCase
        
        mock_workflow_repo.save.return_value = None
        mock_execution_repo.save.return_value = None
        mock_state_store.set_execution_metadata.return_value = None
        mock_state_store.set_execution_status.return_value = None
        
        use_case = SubmitWorkflowUseCase(
            workflow_repository=mock_workflow_repo,
            execution_repository=mock_execution_repo,
            state_store=mock_state_store,
        )
        
        dag_data = {
            "nodes": [
                {"id": "start", "handler": "input", "dependencies": []}
            ]
        }
        
        wf_id, exec_id = await use_case.execute(
            name="Test Workflow",
            dag_json=dag_data,
        )
        
        assert wf_id is not None
        assert exec_id is not None
        mock_workflow_repo.save.assert_called_once()
        mock_execution_repo.save.assert_called_once()


class TestTriggerExecution:
    @pytest.fixture
    def mock_workflow_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_execution_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_state_store(self):
        return AsyncMock()

    @pytest.fixture
    def mock_message_broker(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_trigger_execution_publishes_root_tasks(
        self, mock_workflow_repo, mock_execution_repo, mock_state_store, mock_message_broker
    ):
        from src.application.workflow.use_cases.trigger_execution import TriggerExecutionUseCase
        from src.domain.workflow.entities.execution import Execution
        from src.domain.workflow.entities.workflow import Workflow
        from src.domain.workflow.value_objects.node_status import NodeStatus
        
        dag_json = {
            "nodes": [
                {"id": "start", "handler": "input", "dependencies": []}
            ]
        }
        
        workflow = Workflow(name="Test", dag_json=dag_json)
        execution = Execution(
            id="exec-123",
            workflow_id=workflow.id,
            status=NodeStatus.PENDING,
        )
        
        mock_execution_repo.get_by_id.return_value = execution
        mock_workflow_repo.get_by_id.return_value = workflow
        mock_state_store.get_all_outputs.return_value = {}
        mock_state_store.set_node_status.return_value = None
        mock_message_broker.publish_task.return_value = None
        
        use_case = TriggerExecutionUseCase(
            workflow_repository=mock_workflow_repo,
            execution_repository=mock_execution_repo,
            state_store=mock_state_store,
            message_broker=mock_message_broker,
        )
        
        await use_case.execute("exec-123")
        
        mock_message_broker.publish_task.assert_called()


class TestGetWorkflowStatus:
    @pytest.fixture
    def mock_execution_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_state_store(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_workflow_status_success(
        self, mock_execution_repo, mock_state_store
    ):
        from src.application.workflow.use_cases.get_workflow_status import GetWorkflowStatusUseCase
        from src.domain.workflow.entities.execution import Execution
        from src.domain.workflow.value_objects.node_status import NodeStatus
        
        execution = Execution(
            id="exec-123",
            workflow_id="wf-456",
            status=NodeStatus.RUNNING,
        )
        
        mock_state_store.get_execution_status.return_value = None # Fallback to DB
        mock_state_store.get_execution_metadata.return_value = None
        mock_state_store.get_all_node_statuses.return_value = {"start": NodeStatus.RUNNING}
        mock_execution_repo.get_by_id.return_value = execution
        
        use_case = GetWorkflowStatusUseCase(
            execution_repository=mock_execution_repo,
            state_store=mock_state_store,
        )
        
        result = await use_case.execute("exec-123")
        
        assert result["execution_id"] == "exec-123"
        assert result["status"] == "RUNNING"


class TestCancelWorkflow:
    @pytest.fixture
    def mock_execution_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_state_store(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_cancel_workflow_success(
        self, mock_execution_repo, mock_state_store
    ):
        from src.application.workflow.use_cases.cancel_workflow import CancelWorkflowUseCase
        from src.domain.workflow.entities.execution import Execution
        from src.domain.workflow.value_objects.node_status import NodeStatus
        
        execution = Execution(
            id="exec-123",
            workflow_id="wf-456",
            status=NodeStatus.RUNNING,
        )
        execution.initialize_nodes(["start"])
        
        mock_execution_repo.get_by_id.return_value = execution
        mock_state_store.set_execution_status.return_value = None
        mock_state_store.set_node_status.return_value = None
        
        use_case = CancelWorkflowUseCase(
            execution_repository=mock_execution_repo,
            state_store=mock_state_store,
        )
        
        result = await use_case.execute("exec-123")
        
        assert result is None
        assert execution.status == NodeStatus.CANCELLED
