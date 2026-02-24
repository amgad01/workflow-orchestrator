from enum import Enum


class NodeStatus(str, Enum):
    """
    Enumeration of valid states for a workflow node or execution.

    States:
        PENDING: Initial state, waiting for dependencies.
        RUNNING: Currently executing.
        COMPLETED: Successfully finished.
        FAILED: Execution failed due to error.
        CANCELLED: Execution was manually stopped.
        SKIPPED: Condition evaluated to false.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"

    def can_transition_to(self, target: "NodeStatus") -> bool:
        """
        Validates if a transition from current state to target state is allowed.

        Args:
            target (NodeStatus): The desired next state.

        Returns:
            bool: True if transition is valid, False otherwise.
        """
        valid_transitions = {
            NodeStatus.PENDING: {NodeStatus.RUNNING, NodeStatus.CANCELLED, NodeStatus.SKIPPED},
            NodeStatus.RUNNING: {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.CANCELLED},
            NodeStatus.COMPLETED: set(),
            NodeStatus.FAILED: set(),
            NodeStatus.CANCELLED: set(),
            NodeStatus.SKIPPED: set(),
        }
        return target in valid_transitions[self]
