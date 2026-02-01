import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.secondary.persistence.models import WorkflowModel
from src.domain.workflow.entities.workflow import Workflow
from src.ports.secondary.workflow_repository import IWorkflowRepository


class PostgresWorkflowRepository(IWorkflowRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, workflow: Workflow) -> None:
        model = WorkflowModel(
            id=workflow.id,
            name=workflow.name,
            dag_json=json.dumps(workflow.dag_json),
            created_at=workflow.created_at,
        )
        self._session.add(model)
        await self._session.commit()

    async def get_by_id(self, workflow_id: str) -> Workflow | None:
        result = await self._session.execute(
            select(WorkflowModel).where(WorkflowModel.id == workflow_id)
        )
        model = result.scalar_one_or_none()

        if not model:
            return None

        return Workflow(
            id=model.id,
            name=model.name,
            dag_json=json.loads(model.dag_json),
            created_at=model.created_at,
        )
