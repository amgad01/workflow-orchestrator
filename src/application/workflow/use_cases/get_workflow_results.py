from src.ports.secondary.execution_repository import IExecutionRepository
from src.ports.secondary.state_store import IStateStore


class GetWorkflowResultsUseCase:
    def __init__(
        self,
        execution_repository: IExecutionRepository,
        state_store: IStateStore,
    ):
        self._execution_repository = execution_repository
        self._state_store = state_store

    async def execute(self, execution_id: str) -> dict:
        """
        Aggregates output data from all completed nodes.

        This queries the State Store (Hot Path) to return real-time result data,
        which is critical for the "Scatter-Gather" pattern where downstream
        consumers need results from multiple parallel branches.
        """
        execution = await self._execution_repository.get_by_id(execution_id)
        if not execution:
            from src.domain.workflow.exceptions import ExecutionNotFoundError

            raise ExecutionNotFoundError(execution_id)

        outputs = await self._state_store.get_all_outputs(execution_id)

        return {
            "execution_id": execution_id,
            "workflow_id": execution.workflow_id,
            "outputs": outputs,
        }
