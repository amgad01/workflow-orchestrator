from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from src.domain.workflow.exceptions import InvalidNodeStatusTransitionError
from src.domain.workflow.value_objects.node_status import NodeStatus


@dataclass
class NodeExecution:
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    output: dict = field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def transition_to(self, target: NodeStatus) -> None:
        if not self.status.can_transition_to(target):
            raise InvalidNodeStatusTransitionError(self.node_id, self.status.value, target.value)
        self.status = target

        if target == NodeStatus.RUNNING:
            self.started_at = datetime.now(timezone.utc)
        elif target in (NodeStatus.COMPLETED, NodeStatus.FAILED):
            self.completed_at = datetime.now(timezone.utc)


@dataclass
class Execution:
    """
    Aggregate Root representing a single run of a Workflow.
    
    This entity manages the lifecycle of all nodes within the execution. It acts
    as the consistency boundary for state transitions - ensuring that node statuses
    only change in valid ways and that the overall execution status reflects the
    aggregate state of its nodes.
    """
    workflow_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: NodeStatus = NodeStatus.PENDING
    node_states: dict[str, NodeExecution] = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    timeout_seconds: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def initialize_nodes(self, node_ids: list[str]) -> None:
        for node_id in node_ids:
            self.node_states[node_id] = NodeExecution(node_id=node_id)

    def get_node_status(self, node_id: str) -> NodeStatus:
        return self.node_states[node_id].status

    def set_node_running(self, node_id: str) -> None:
        self.node_states[node_id].transition_to(NodeStatus.RUNNING)
        if self.status == NodeStatus.PENDING:
            self.status = NodeStatus.RUNNING
            self.started_at = datetime.now(timezone.utc)

    def set_node_completed(self, node_id: str, output: dict) -> None:
        node = self.node_states[node_id]
        node.transition_to(NodeStatus.COMPLETED)
        node.output = output

    def set_node_failed(self, node_id: str, error: str) -> None:
        node = self.node_states[node_id]
        node.transition_to(NodeStatus.FAILED)
        node.error = error
        self.status = NodeStatus.FAILED

    def is_node_ready(self, node_id: str, dependencies: tuple[str, ...]) -> bool:
        """
        Determines if a node is ready to run based on its dependencies.
        
        Logic:
        1. Node must be PENDING (not already run).
        2. ALL parent dependencies must be COMPLETED.
        
        This strict check prevents race conditions in Fan-In scenarios.
        """
        if self.get_node_status(node_id) != NodeStatus.PENDING:
            return False
        return all(
            self.get_node_status(dep) == NodeStatus.COMPLETED for dep in dependencies
        )

    def all_nodes_complete(self) -> bool:
        return all(
            node.status == NodeStatus.COMPLETED for node in self.node_states.values()
        )

    def has_failed(self) -> bool:
        return any(
            node.status == NodeStatus.FAILED for node in self.node_states.values()
        )

    def get_outputs(self) -> dict[str, dict]:
        return {
            node_id: node.output
            for node_id, node in self.node_states.items()
            if node.status == NodeStatus.COMPLETED
        }

    def mark_complete(self) -> None:
        self.status = NodeStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)

    def cancel(self) -> None:
        """
        Cancels the execution and stops all pending work.
        
        Cascading Effect:
        - Marks the execution as CANCELLED.
        - Iterates through all nodes: Any node that is PENDING or RUNNING is 
          immediately transitioned to CANCELLED to prevent workers from picking it up
          or to signal active workers to stop (via state check).
        """
        self.status = NodeStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)
        for node in self.node_states.values():
            if node.status in (NodeStatus.PENDING, NodeStatus.RUNNING):
                node.transition_to(NodeStatus.CANCELLED)
