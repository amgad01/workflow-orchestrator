from src.ports.secondary.execution_repository import IExecutionRepository
from src.ports.secondary.state_store import IStateStore


class CancelWorkflowUseCase:
    def __init__(
        self,
        execution_repository: IExecutionRepository,
        state_store: IStateStore,
    ):
        self._execution_repository = execution_repository
        self._state_store = state_store

    async def execute(self, execution_id: str) -> None:
        """
        Cancels an active execution.
        
        Logic:
        1. Updates the persisted execution state to CANCELLED (Cold Store).
        2. Syncs the status to Redis (Hot Store) to safeguard against race conditions.
        3. Marks all active nodes as CANCELLED to prevent workers from picking them up.
        """
        execution = await self._execution_repository.get_by_id(execution_id)
        if not execution:
            from src.domain.workflow.exceptions import ExecutionNotFoundError
            raise ExecutionNotFoundError(execution_id)

        execution.cancel()
        await self._execution_repository.update(execution)

        # Update execution status in state store (Hot Path)
        await self._state_store.set_execution_status(execution_id, execution.status)

        # Also update all individual nodes in state store to stop further dispatching
        for node_id, node_state in execution.node_states.items():
            await self._state_store.set_node_status(execution_id, node_id, node_state.status)
