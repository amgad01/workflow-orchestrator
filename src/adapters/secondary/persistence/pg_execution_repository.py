import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.secondary.persistence.models import ExecutionModel
from src.domain.workflow.entities.execution import Execution
from src.domain.workflow.value_objects.node_status import NodeStatus
from src.ports.secondary.execution_repository import IExecutionRepository


class PostgresExecutionRepository(IExecutionRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, execution: Execution) -> None:
        model = ExecutionModel(
            id=execution.id,
            workflow_id=execution.workflow_id,
            status=execution.status.value,
            params=json.dumps(execution.params),
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            timeout_seconds=execution.timeout_seconds,
        )
        self._session.add(model)
        await self._session.commit()

    async def get_by_id(self, execution_id: str) -> Execution | None:
        result = await self._session.execute(
            select(ExecutionModel).where(ExecutionModel.id == execution_id)
        )
        model = result.scalar_one_or_none()

        if not model:
            return None

        return Execution(
            id=model.id,
            workflow_id=model.workflow_id,
            status=NodeStatus(model.status),
            params=json.loads(model.params),
            timeout_seconds=model.timeout_seconds,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
        )

    async def update(self, execution: Execution) -> None:
        result = await self._session.execute(
            select(ExecutionModel).where(ExecutionModel.id == execution.id)
        )
        model = result.scalar_one_or_none()

        if model:
            model.status = execution.status.value
            model.started_at = execution.started_at
            model.completed_at = execution.completed_at
            await self._session.commit()

    async def get_running_executions(self) -> list[Execution]:
        result = await self._session.execute(
            select(ExecutionModel).where(ExecutionModel.status == NodeStatus.RUNNING.value)
        )
        models = result.scalars().all()
        return [
            Execution(
                id=model.id,
                workflow_id=model.workflow_id,
                status=NodeStatus(model.status),
                params=json.loads(model.params),
                timeout_seconds=model.timeout_seconds,
                created_at=model.created_at,
                started_at=model.started_at,
                completed_at=model.completed_at,
            )
            for model in models
        ]
