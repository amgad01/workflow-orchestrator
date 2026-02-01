import pytest
from unittest.mock import AsyncMock, MagicMock
from src.adapters.secondary.persistence.pg_workflow_repository import PostgresWorkflowRepository
from src.adapters.secondary.persistence.pg_execution_repository import PostgresExecutionRepository
from src.adapters.secondary.persistence.models import WorkflowModel, ExecutionModel
from src.domain.workflow.entities.workflow import Workflow
from src.domain.workflow.entities.execution import Execution
from src.domain.workflow.value_objects.node_status import NodeStatus


class TestPgWorkflowRepository:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_save_workflow(self, mock_session):
        repo = PostgresWorkflowRepository(mock_session)
        workflow = Workflow(name="Test", dag_json={})
        
        await repo.save(workflow)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_workflow(self, mock_session):
        repo = PostgresWorkflowRepository(mock_session)
        mock_model = WorkflowModel(id="w1", name="Test", dag_json="{}")
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        mock_session.execute.return_value = mock_result
        
        result = await repo.get_by_id("w1")
        assert result.id == "w1"
        assert result.name == "Test"


class TestPgExecutionRepository:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_save_execution(self, mock_session):
        repo = PostgresExecutionRepository(mock_session)
        execution = Execution(workflow_id="w1")
        
        await repo.save(execution)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_execution(self, mock_session):
        repo = PostgresExecutionRepository(mock_session)
        mock_model = ExecutionModel(id="e1", workflow_id="w1", status="PENDING", params="{}")
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        mock_session.execute.return_value = mock_result
        
        result = await repo.get_by_id("e1")
        assert result.id == "e1"
        assert result.status == NodeStatus.PENDING

    @pytest.mark.asyncio
    async def test_update_execution(self, mock_session):
        repo = PostgresExecutionRepository(mock_session)
        execution = Execution(id="e1", workflow_id="w1", status=NodeStatus.RUNNING)
        
        mock_model = ExecutionModel(id="e1", workflow_id="w1", status="PENDING")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        mock_session.execute.return_value = mock_result
        
        await repo.update(execution)
        assert mock_model.status == "RUNNING"
        mock_session.commit.assert_called_once()
