from src.ports.secondary.execution_repository import IExecutionRepository
import datetime
from src.domain.workflow.value_objects.dag import DAG
from src.domain.workflow.value_objects.node_status import NodeStatus
from src.domain.workflow.value_objects.template import TemplateResolver
from src.ports.secondary.message_broker import IMessageBroker, TaskMessage
from src.ports.secondary.state_store import IStateStore
from src.ports.secondary.workflow_repository import IWorkflowRepository

class TriggerExecutionUseCase:
    """
    Use case for triggering the start of a pending execution.
    
    This initiates the workflow by:
    1. Validating the execution existence and state.
    2. Identifying root nodes (zero dependencies).
    3. Resolving templates for root nodes.
    4. Publishing initial tasks to the message broker.
    5. Updating system state to RUNNING.
    """
    def __init__(
        self,
        workflow_repository: IWorkflowRepository,
        execution_repository: IExecutionRepository,
        state_store: IStateStore,
        message_broker: IMessageBroker,
    ):
        self._workflow_repository = workflow_repository
        self._execution_repository = execution_repository
        self._state_store = state_store
        self._message_broker = message_broker

    async def execute(self, execution_id: str, params=None) -> None:
        """
        Triggers the execution causing it to transition from PENDING -> RUNNING.

        Bootstrap Logic:
        1. Validates Workflow and Execution existence.
        2. Injects runtime parameters (if any) into the State Store.
        3. Identifies Root Nodes (Dependency-free nodes) from the DAG.
        4. Dispatches initial tasks to the Message Broker.
        5. Bootstraps Redis Metadata (Hot Path) so the Orchestrator can run without DB hits.
        
        Args:
            execution_id: The execution to start.
            params: Runtime parameters/inputs.
            
        Raises:
            ExecutionNotFoundError: If execution doesn't exist.
            InvalidWorkflowError: If workflow definition is missing.
        """
        execution = await self._execution_repository.get_by_id(execution_id)
        if not execution:
            from src.domain.workflow.exceptions import ExecutionNotFoundError
            raise ExecutionNotFoundError(execution_id)

        workflow = await self._workflow_repository.get_by_id(execution.workflow_id)
        if not workflow:
            from src.domain.workflow.exceptions import InvalidWorkflowError
            raise InvalidWorkflowError(f"Workflow {execution.workflow_id} not found")

        dag = DAG.from_json(workflow.dag_json)

        if params:
            await self._state_store.set_node_output(execution_id, "params", params)

        root_nodes = dag.get_root_nodes()
        outputs = await self._state_store.get_all_outputs(execution_id)

        # Set execution to running if we have nodes to start
        if root_nodes and execution.status == NodeStatus.PENDING:
            execution.status = NodeStatus.RUNNING
            execution.started_at = datetime.datetime.now(datetime.timezone.utc)
            await self._execution_repository.update(execution)

        for node_id in root_nodes:
            node = dag.nodes[node_id]
            resolved_config = TemplateResolver.resolve_config(node.config, outputs)

            task = TaskMessage(
                id=f"{execution_id}:{node_id}",
                execution_id=execution_id,
                node_id=node_id,
                handler=node.handler,
                config=resolved_config,
            )

            await self._state_store.set_node_status(execution_id, node_id, NodeStatus.RUNNING)
            await self._message_broker.publish_task(task)

        # Populate Redis Metadata for Zero-DB Hot Path
        await self._state_store.set_execution_status(execution_id, NodeStatus.RUNNING)
        await self._state_store.set_execution_metadata(execution_id, {
            "workflow_id": execution.workflow_id,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "timeout_seconds": execution.timeout_seconds
        })
