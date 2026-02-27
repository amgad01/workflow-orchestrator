import pytest

from src.domain.workflow.exceptions import (
    CyclicDependencyError,
    EmptyWorkflowError,
    InvalidNodeReferenceError,
)
from src.domain.workflow.value_objects.dag import DAG


def test_dag_creation_success():
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": []},
            {"id": "B", "handler": "h1", "dependencies": ["A"]},
            {"id": "C", "handler": "h1", "dependencies": ["B"]},
        ]
    }
    dag = DAG.from_json(data)
    assert len(dag.nodes) == 3
    assert dag.get_dependencies("B") == ("A",)


def test_dag_cycle_detection():
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": ["C"]},
            {"id": "B", "handler": "h1", "dependencies": ["A"]},
            {"id": "C", "handler": "h1", "dependencies": ["B"]},
        ]
    }
    with pytest.raises(CyclicDependencyError):
        DAG.from_json(data)


def test_dag_self_loop_detection():
    data = {"nodes": [{"id": "A", "handler": "h1", "dependencies": ["A"]}]}
    with pytest.raises(CyclicDependencyError):
        DAG.from_json(data)


def test_dag_invalid_reference():
    data = {"nodes": [{"id": "A", "handler": "h1", "dependencies": ["Z"]}]}
    with pytest.raises(InvalidNodeReferenceError):
        DAG.from_json(data)


def test_dag_empty():
    data = {"nodes": []}
    with pytest.raises(EmptyWorkflowError):
        DAG.from_json(data)


def test_dag_disjoint_graph():
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": []},
            {"id": "B", "handler": "h1", "dependencies": []},
        ]
    }
    dag = DAG.from_json(data)
    assert len(dag.nodes) == 2


def test_topological_sort_deterministic():
    """Verify topological sort produces a valid, deterministic ordering."""
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": []},
            {"id": "B", "handler": "h1", "dependencies": ["A"]},
            {"id": "C", "handler": "h1", "dependencies": ["A"]},
            {"id": "D", "handler": "h1", "dependencies": ["B", "C"]},
        ]
    }
    dag = DAG.from_json(data)
    order = dag.topological_sort()
    assert order[0] == "A"
    assert order[-1] == "D"
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")
    assert len(order) == 4


def test_topological_sort_large_fan_out():
    """Ensure deque-based sort handles wide fan-out correctly."""
    nodes = [{"id": "root", "handler": "h1", "dependencies": []}]
    for i in range(50):
        nodes.append({"id": f"child_{i}", "handler": "h1", "dependencies": ["root"]})
    nodes.append({"id": "sink", "handler": "h1", "dependencies": [f"child_{i}" for i in range(50)]})
    dag = DAG.from_json({"nodes": nodes})
    order = dag.topological_sort()
    assert order[0] == "root"
    assert order[-1] == "sink"
    assert len(order) == 52


def test_get_root_nodes():
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": []},
            {"id": "B", "handler": "h1", "dependencies": []},
            {"id": "C", "handler": "h1", "dependencies": ["A", "B"]},
        ]
    }
    dag = DAG.from_json(data)
    roots = dag.get_root_nodes()
    assert set(roots) == {"A", "B"}


def test_get_dependents():
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": []},
            {"id": "B", "handler": "h1", "dependencies": ["A"]},
            {"id": "C", "handler": "h1", "dependencies": ["A"]},
        ]
    }
    dag = DAG.from_json(data)
    assert dag.get_dependents("A") == {"B", "C"}
