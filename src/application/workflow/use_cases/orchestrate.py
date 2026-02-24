import logging
from datetime import datetime, timezone

from src.domain.workflow.value_objects.dag import DAG
from src.domain.workflow.value_objects.node_status import NodeStatus
from src.domain.workflow.value_objects.template import TemplateResolver
from src.ports.secondary.execution_repository import IExecutionRepository
from src.ports.secondary.message_broker import CompletionMessage, IMessageBroker, TaskMessage
from src.ports.secondary.metrics import IMetrics
from src.ports.secondary.state_store import IStateStore
from src.ports.secondary.workflow_repository import IWorkflowRepository

logger = logging.getLogger(__name__)


class OrchestrateUseCase:
    """Reacts to task completions, resolves dependencies, and dispatches next tasks."""

    _dag_cache = {}

    def __init__(
        self,
        workflow_repository: IWorkflowRepository,
        execution_repository: IExecutionRepository,
        state_store: IStateStore,
        message_broker: IMessageBroker,
        metrics: IMetrics | None = None,
    ):
        self._workflow_repository = workflow_repository
        self._execution_repository = execution_repository
        self._state_store = state_store
        self._message_broker = message_broker
        self._metrics = metrics

    async def _get_workflow_dag(self, workflow_id: str) -> DAG | None:
        if workflow_id in self._dag_cache:
            return self._dag_cache[workflow_id]

        workflow = await self._workflow_repository.get_by_id(workflow_id)
        if workflow:
            dag = DAG.from_json(workflow.dag_json)
            self._dag_cache[workflow_id] = dag
            return dag
        return None

    async def handle_completion(self, completion: CompletionMessage) -> None:
        """Process a task completion: update state, check for failures, dispatch next nodes."""
        cached_status = await self._state_store.get_execution_status(completion.execution_id)
        if cached_status in (NodeStatus.CANCELLED, NodeStatus.FAILED, NodeStatus.COMPLETED):
            return
        if completion.success:
            await self._state_store.set_node_status(
                completion.execution_id, completion.node_id, NodeStatus.COMPLETED
            )
            if completion.output:
                await self._state_store.set_node_output(
                    completion.execution_id, completion.node_id, completion.output
                )
        else:
            await self._state_store.set_node_status(
                completion.execution_id, completion.node_id, NodeStatus.FAILED
            )
            execution = await self._execution_repository.get_by_id(completion.execution_id)
            if execution:
                await self._fail_execution(execution, "Task failed")
            return

        await self._dispatch_ready_nodes(completion.execution_id)

    async def _dispatch_ready_nodes(self, execution_id: str) -> None:
        """Find pending nodes with all dependencies met, acquire lock, resolve templates, dispatch."""
        metadata = await self._state_store.get_execution_metadata(execution_id)
        workflow_id = metadata.get("workflow_id") if metadata else None

        if not workflow_id:
            execution = await self._execution_repository.get_by_id(execution_id)
            if execution:
                workflow_id = execution.workflow_id
            else:
                return

        dag = await self._get_workflow_dag(workflow_id)
        if not dag:
            return

        node_statuses = await self._state_store.get_all_node_statuses(execution_id)
        pending_nodes = [n for n, s in node_statuses.items() if s == NodeStatus.PENDING]

        if not pending_nodes:
            if all(s in (NodeStatus.COMPLETED, NodeStatus.SKIPPED) for s in node_statuses.values()):
                execution = await self._execution_repository.get_by_id(execution_id)
                if execution and execution.status != NodeStatus.COMPLETED:
                    if await self._check_timeout(execution):
                        return

                    execution.mark_complete()
                    await self._execution_repository.update(execution)
                    await self._state_store.set_execution_status(execution_id, NodeStatus.COMPLETED)
            return

        outputs = await self._state_store.get_all_outputs(execution_id)
        for node_id in pending_nodes:
            dependencies = dag.get_dependencies(node_id)
            if all(node_statuses.get(dep) in (NodeStatus.COMPLETED, NodeStatus.SKIPPED) for dep in dependencies):
                lock_key = f"dispatch:{execution_id}:{node_id}"
                if await self._state_store.acquire_lock(lock_key):
                    try:
                        # Double-check status after lock
                        current_status = await self._state_store.get_node_status(execution_id, node_id)
                        if current_status != NodeStatus.PENDING:
                            continue

                        node = dag.nodes[node_id]
                        if not TemplateResolver.evaluate_condition(node.condition, outputs):
                            await self._state_store.set_node_status(execution_id, node_id, NodeStatus.SKIPPED)
                            await self._message_broker.publish_completion(CompletionMessage(
                                id=f"{execution_id}:{node_id}", execution_id=execution_id, node_id=node_id, success=True, output=None
                            ))
                            continue

                        task = TaskMessage(
                            id=f"{execution_id}:{node_id}",
                            execution_id=execution_id,
                            node_id=node_id,
                            handler=node.handler,
                            config=TemplateResolver.resolve_config(node.config, outputs),
                        )
                        await self._state_store.set_node_status(execution_id, node_id, NodeStatus.RUNNING)
                        await self._message_broker.publish_task(task)
                    finally:
                        await self._state_store.release_lock(lock_key)

    async def check_all_timeouts(self) -> None:
        running_executions = await self._execution_repository.get_running_executions()
        for execution in running_executions:
            await self._check_timeout(execution)

    async def _check_timeout(self, execution) -> bool:
        if execution.status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.CANCELLED):
            return False
        
        if execution.timeout_seconds and execution.started_at:
            now = datetime.now(timezone.utc)
            elapsed = (now - execution.started_at).total_seconds()
            
            if elapsed > execution.timeout_seconds:
                logger.warning(f"Workflow {execution.id} timed out: {elapsed}s > {execution.timeout_seconds}s")
                await self._fail_execution(execution, f"Workflow timed out after {execution.timeout_seconds}s")
                return True
            else:
                logger.debug(f"Workflow {execution.id} within timeout: {elapsed}s <= {execution.timeout_seconds}s")
        
        return False

    async def _fail_execution(self, execution, error_message: str) -> None:
        execution.status = NodeStatus.FAILED
        await self._execution_repository.update(execution)
        await self._state_store.set_execution_status(execution.id, NodeStatus.FAILED)

        if execution.started_at and self._metrics:
            duration = (datetime.now(timezone.utc) - execution.started_at).total_seconds()
            self._metrics.record_workflow_completion(execution.workflow_id, "FAILED", duration)
        
        node_statuses = await self._state_store.get_all_node_statuses(execution.id)
        for node_id, status in node_statuses.items():
            if status in (NodeStatus.PENDING, NodeStatus.RUNNING):
                await self._state_store.set_node_status(execution.id, node_id, NodeStatus.FAILED)
