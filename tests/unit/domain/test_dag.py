import pytest
from src.domain.workflow.value_objects.dag import DAG
from src.domain.workflow.exceptions import CyclicDependencyError, InvalidNodeReferenceError, EmptyWorkflowError

def test_dag_creation_success():
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": []},
            {"id": "B", "handler": "h1", "dependencies": ["A"]},
            {"id": "C", "handler": "h1", "dependencies": ["B"]}
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
            {"id": "C", "handler": "h1", "dependencies": ["B"]}
        ]
    }
    with pytest.raises(CyclicDependencyError):
        DAG.from_json(data)

def test_dag_self_loop_detection():
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": ["A"]}
        ]
    }
    with pytest.raises(CyclicDependencyError):
        DAG.from_json(data)

def test_dag_invalid_reference():
    data = {
        "nodes": [
            {"id": "A", "handler": "h1", "dependencies": ["Z"]}
        ]
    }
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
            {"id": "B", "handler": "h1", "dependencies": []}
        ]
    }
    dag = DAG.from_json(data)
    assert len(dag.nodes) == 2
