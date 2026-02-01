import pytest

from src.domain.workflow.exceptions import (
    CyclicDependencyError,
    DuplicateNodeIdError,
    EmptyWorkflowError,
    InvalidNodeReferenceError,
)
from src.domain.workflow.value_objects.dag import DAG


class TestDAGValidation:
    def test_valid_linear_dag(self):
        data = {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "process", "dependencies": ["A"]},
                {"id": "C", "handler": "output", "dependencies": ["B"]},
            ]
        }

        dag = DAG.from_json(data)

        assert len(dag.nodes) == 3
        assert dag.get_root_nodes() == ["A"]
        assert dag.get_dependents("A") == {"B"}
        assert dag.get_dependents("B") == {"C"}

    def test_valid_fanout_fanin_dag(self):
        data = {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "process", "dependencies": ["A"]},
                {"id": "C", "handler": "process", "dependencies": ["A"]},
                {"id": "D", "handler": "output", "dependencies": ["B", "C"]},
            ]
        }

        dag = DAG.from_json(data)

        assert len(dag.nodes) == 4
        assert dag.get_root_nodes() == ["A"]
        assert dag.get_dependents("A") == {"B", "C"}
        assert dag.get_dependencies("D") == ("B", "C")

    def test_detects_simple_cycle(self):
        data = {
            "nodes": [
                {"id": "A", "handler": "process", "dependencies": ["B"]},
                {"id": "B", "handler": "process", "dependencies": ["A"]},
            ]
        }

        with pytest.raises(CyclicDependencyError) as exc_info:
            DAG.from_json(data)

        assert "A" in exc_info.value.cycle_nodes or "B" in exc_info.value.cycle_nodes

    def test_detects_complex_cycle(self):
        data = {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "process", "dependencies": ["A", "D"]},
                {"id": "C", "handler": "process", "dependencies": ["B"]},
                {"id": "D", "handler": "process", "dependencies": ["C"]},
            ]
        }

        with pytest.raises(CyclicDependencyError):
            DAG.from_json(data)

    def test_detects_self_reference(self):
        data = {
            "nodes": [
                {"id": "A", "handler": "process", "dependencies": ["A"]},
            ]
        }

        with pytest.raises(CyclicDependencyError):
            DAG.from_json(data)

    def test_rejects_invalid_node_reference(self):
        data = {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "process", "dependencies": ["A", "X"]},
            ]
        }

        with pytest.raises(InvalidNodeReferenceError) as exc_info:
            DAG.from_json(data)

        assert exc_info.value.node_id == "B"
        assert exc_info.value.missing_dependency == "X"

    def test_rejects_duplicate_node_ids(self):
        data = {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "A", "handler": "process", "dependencies": []},
            ]
        }

        with pytest.raises(DuplicateNodeIdError) as exc_info:
            DAG.from_json(data)

        assert exc_info.value.node_id == "A"

    def test_rejects_empty_workflow(self):
        data = {"nodes": []}

        with pytest.raises(EmptyWorkflowError):
            DAG.from_json(data)

    def test_topological_sort_linear(self):
        data = {
            "nodes": [
                {"id": "C", "handler": "output", "dependencies": ["B"]},
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "process", "dependencies": ["A"]},
            ]
        }

        dag = DAG.from_json(data)
        order = dag.topological_sort()

        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_topological_sort_parallel(self):
        data = {
            "nodes": [
                {"id": "A", "handler": "input", "dependencies": []},
                {"id": "B", "handler": "process", "dependencies": ["A"]},
                {"id": "C", "handler": "process", "dependencies": ["A"]},
                {"id": "D", "handler": "output", "dependencies": ["B", "C"]},
            ]
        }

        dag = DAG.from_json(data)
        order = dag.topological_sort()

        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")
