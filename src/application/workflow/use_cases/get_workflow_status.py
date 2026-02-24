from src.domain.workflow.value_objects.node_status import NodeStatus
from src.ports.secondary.execution_repository import IExecutionRepository
from src.ports.secondary.state_store import IStateStore


class GetWorkflowStatusUseCase:
    def __init__(
        self,
        execution_repository: IExecutionRepository,
        state_store: IStateStore,
    ):
        self._execution_repository = execution_repository
        self._state_store = state_store

    async def execute(self, execution_id: str) -> dict:
        """
        Retrieves the current status of a workflow execution.

        Architecture Note (Hot Path):
        Attempts to read from Redis (Hot State) first for sub-millisecond latency.
        Falls back to PostgreSQL (Cold State) if the execution is archived/not found in cache.
        """
        cached_status = await self._state_store.get_execution_status(execution_id)
        cached_metadata = await self._state_store.get_execution_metadata(execution_id)

        node_statuses = await self._state_store.get_all_node_statuses(execution_id)

        if cached_status and cached_metadata:
            return {
                "execution_id": execution_id,
                "workflow_id": cached_metadata["workflow_id"],
                "status": cached_status.value,
                "node_statuses": {
                    node_id: status.value for node_id, status in node_statuses.items()
                },
            }

        execution = await self._execution_repository.get_by_id(execution_id)
        if not execution:
            from src.domain.workflow.exceptions import ExecutionNotFoundError

            raise ExecutionNotFoundError(execution_id)

        all_completed = all(s == NodeStatus.COMPLETED for s in node_statuses.values())
        any_failed = any(s == NodeStatus.FAILED for s in node_statuses.values())
        any_running = any(s == NodeStatus.RUNNING for s in node_statuses.values())

        if execution.status == NodeStatus.CANCELLED:
            overall_status = NodeStatus.CANCELLED
        elif any_failed:
            overall_status = NodeStatus.FAILED
        elif all_completed and node_statuses:
            overall_status = NodeStatus.COMPLETED
        elif any_running:
            overall_status = NodeStatus.RUNNING
        else:
            overall_status = NodeStatus.PENDING

        return {
            "execution_id": execution_id,
            "workflow_id": execution.workflow_id,
            "status": overall_status.value,
            "node_statuses": {node_id: status.value for node_id, status in node_statuses.items()},
        }
