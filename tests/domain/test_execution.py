import pytest

from src.domain.workflow.entities.execution import Execution, NodeExecution
from src.domain.workflow.exceptions import InvalidNodeStatusTransitionError
from src.domain.workflow.value_objects.node_status import NodeStatus


class TestNodeStatus:
    def test_pending_can_transition_to_running(self):
        assert NodeStatus.PENDING.can_transition_to(NodeStatus.RUNNING)

    def test_pending_cannot_transition_to_completed(self):
        assert not NodeStatus.PENDING.can_transition_to(NodeStatus.COMPLETED)

    def test_running_can_transition_to_completed(self):
        assert NodeStatus.RUNNING.can_transition_to(NodeStatus.COMPLETED)

    def test_running_can_transition_to_failed(self):
        assert NodeStatus.RUNNING.can_transition_to(NodeStatus.FAILED)

    def test_completed_cannot_transition(self):
        assert not NodeStatus.COMPLETED.can_transition_to(NodeStatus.PENDING)
        assert not NodeStatus.COMPLETED.can_transition_to(NodeStatus.RUNNING)
        assert not NodeStatus.COMPLETED.can_transition_to(NodeStatus.FAILED)


class TestExecution:
    def test_initialize_nodes(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A", "B", "C"])

        assert len(execution.node_states) == 3
        assert all(n.status == NodeStatus.PENDING for n in execution.node_states.values())

    def test_set_node_running_updates_execution_status(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A"])

        execution.set_node_running("A")

        assert execution.node_states["A"].status == NodeStatus.RUNNING
        assert execution.status == NodeStatus.RUNNING
        assert execution.started_at is not None

    def test_set_node_completed(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A"])
        execution.set_node_running("A")

        execution.set_node_completed("A", {"result": "success"})

        assert execution.node_states["A"].status == NodeStatus.COMPLETED
        assert execution.node_states["A"].output == {"result": "success"}

    def test_set_node_failed_marks_execution_failed(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A"])
        execution.set_node_running("A")

        execution.set_node_failed("A", "Some error")

        assert execution.node_states["A"].status == NodeStatus.FAILED
        assert execution.status == NodeStatus.FAILED

    def test_is_node_ready_with_no_dependencies(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A"])

        assert execution.is_node_ready("A", tuple())

    def test_is_node_ready_with_completed_dependencies(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A", "B"])
        execution.set_node_running("A")
        execution.set_node_completed("A", {})

        assert execution.is_node_ready("B", ("A",))

    def test_is_node_ready_with_pending_dependencies(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A", "B"])

        assert not execution.is_node_ready("B", ("A",))

    def test_all_nodes_complete(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A", "B"])
        execution.set_node_running("A")
        execution.set_node_completed("A", {})
        execution.set_node_running("B")
        execution.set_node_completed("B", {})

        assert execution.all_nodes_complete()

    def test_get_outputs(self):
        execution = Execution(workflow_id="wf-1")
        execution.initialize_nodes(["A", "B"])
        execution.set_node_running("A")
        execution.set_node_completed("A", {"x": 1})
        execution.set_node_running("B")
        execution.set_node_completed("B", {"y": 2})

        outputs = execution.get_outputs()

        assert outputs == {"A": {"x": 1}, "B": {"y": 2}}


class TestNodeExecution:
    def test_invalid_transition_raises_error(self):
        node = NodeExecution(node_id="A")

        with pytest.raises(InvalidNodeStatusTransitionError):
            node.transition_to(NodeStatus.COMPLETED)
