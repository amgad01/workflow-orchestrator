from datetime import datetime, timezone

from src.domain.workflow.entities.execution import Execution
from src.domain.workflow.entities.workflow import Workflow
from src.domain.workflow.value_objects.dag import DAG
from src.domain.workflow.value_objects.node_status import NodeStatus
from src.ports.secondary.execution_repository import IExecutionRepository
from src.ports.secondary.state_store import IStateStore
from src.ports.secondary.workflow_repository import IWorkflowRepository


class SubmitWorkflowUseCase:
    """
    Use case for submitting a new workflow.

    Responsibilities:
    1. Parse and validate the DAG structure (via Domain entities).
    2. Persist the workflow definition and initial execution record.
    3. Initialize the operational state in Redis (Hot Path) for immediate accessibility.
    """
    def __init__(
        self,
        workflow_repository: IWorkflowRepository,
        execution_repository: IExecutionRepository,
        state_store: IStateStore,
    ):
        self._workflow_repository = workflow_repository
        self._execution_repository = execution_repository
        self._state_store = state_store

    async def execute(self, name: str, dag_json: dict, timeout_seconds: float | None = None) -> tuple[str, str]:
        """
        Submits a workflow for execution.

        Process:
        1. Parses and Validates the DAG (Cycle Detection).
        2. Persists the workflow definition to PostgreSQL (System of Record).
        3. Initializes the Execution state in Redis (Hot Path).
        
        Args:
            name: Workflow name.
            dag_json: The raw DAG definition.
            timeout_seconds: Optional execution timeout.

        Returns:
            tuple containing (workflow_id, execution_id).
        """
        dag = DAG.from_json(dag_json)

        workflow = Workflow(name=name, dag_json=dag_json)
        await self._workflow_repository.save(workflow)

        execution = Execution(workflow_id=workflow.id, timeout_seconds=timeout_seconds)
        execution.initialize_nodes(list(dag.nodes.keys()))
        await self._execution_repository.save(execution)

        metadata = {"workflow_id": workflow.id}
        if timeout_seconds:
            timeout_at = datetime.now(timezone.utc).timestamp() + timeout_seconds
            timeout_at_dt = datetime.fromtimestamp(timeout_at, tz=timezone.utc)
            metadata["timeout_at"] = timeout_at_dt.isoformat()

        await self._state_store.set_execution_metadata(execution.id, metadata)
        await self._state_store.set_execution_status(execution.id, NodeStatus.PENDING)

        for node_id in dag.nodes:
            await self._state_store.set_node_status(
                execution.id, node_id, execution.get_node_status(node_id)
            )

        return workflow.id, execution.id
