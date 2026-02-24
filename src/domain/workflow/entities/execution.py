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
    """Aggregate root for a single workflow run. Manages node lifecycle and status transitions."""

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
        """True if node is PENDING and all dependencies are COMPLETED."""
        if self.get_node_status(node_id) != NodeStatus.PENDING:
            return False
        return all(self.get_node_status(dep) == NodeStatus.COMPLETED for dep in dependencies)

    def all_nodes_complete(self) -> bool:
        return all(node.status == NodeStatus.COMPLETED for node in self.node_states.values())

    def has_failed(self) -> bool:
        return any(node.status == NodeStatus.FAILED for node in self.node_states.values())

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
        """Cancel execution and mark all pending/running nodes as CANCELLED."""
        self.status = NodeStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)
        for node in self.node_states.values():
            if node.status in (NodeStatus.PENDING, NodeStatus.RUNNING):
                node.transition_to(NodeStatus.CANCELLED)
