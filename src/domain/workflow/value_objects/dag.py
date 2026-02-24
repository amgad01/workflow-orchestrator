from collections import defaultdict
from dataclasses import dataclass, field

from src.domain.workflow.exceptions import (
    CyclicDependencyError,
    DuplicateNodeIdError,
    EmptyWorkflowError,
    InvalidNodeReferenceError,
)


@dataclass(frozen=True)
class NodeDefinition:
    """Immutable node definition used during DAG validation and traversal."""
    id: str
    handler: str
    dependencies: tuple[str, ...]
    config: dict = field(default_factory=dict)
    condition: str | None = None

    def validate(self) -> None:
        if self.handler == "call_external_service":
            if "url" in self.config and not isinstance(self.config["url"], str):
                raise ValueError(f"Node {self.id}: 'url' must be a string")
        elif self.handler == "call_llm":
            if "prompt" not in self.config:
                pass 
            elif not isinstance(self.config["prompt"], str):
                 raise ValueError(f"Node {self.id}: 'prompt' must be a string")


@dataclass
class DAG:
    """Validated DAG structure with cycle detection (Kahn's algorithm) and traversal methods."""

    nodes: dict[str, NodeDefinition] = field(default_factory=dict)
    adjacency: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    reverse_adjacency: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @classmethod
    def from_json(cls, data: dict) -> "DAG":
        """Parse, build, and validate a DAG from a raw JSON payload."""
        dag = cls()
        node_list = data.get("nodes", [])

        if not node_list:
            raise EmptyWorkflowError()

        for node_data in node_list:
            node_id = node_data["id"]

            if node_id in dag.nodes:
                raise DuplicateNodeIdError(node_id)

            node = NodeDefinition(
                id=node_id,
                handler=node_data["handler"],
                dependencies=tuple(node_data.get("dependencies", [])),
                config=node_data.get("config", {}),
                condition=node_data.get("condition"),
            )
            node.validate()
            dag.nodes[node_id] = node

        dag._build_adjacency_lists()
        dag._validate_references()
        dag._detect_cycles()

        return dag

    def _build_adjacency_lists(self) -> None:
        for node_id, node in self.nodes.items():
            for dep in node.dependencies:
                self.adjacency[dep].add(node_id)
                self.reverse_adjacency[node_id].add(dep)

    def _validate_references(self) -> None:
        for node_id, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    raise InvalidNodeReferenceError(node_id, dep)

    def _detect_cycles(self) -> None:
        """Kahn's algorithm: iteratively remove zero in-degree nodes; remaining nodes form a cycle."""
        in_degree = {node_id: len(deps) for node_id, deps in self.reverse_adjacency.items()}
        for node_id in self.nodes:
            if node_id not in in_degree:
                in_degree[node_id] = 0

        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        visited_count = 0

        while queue:
            current = queue.pop(0)
            visited_count += 1

            for neighbor in self.adjacency.get(current, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(self.nodes):
            unvisited = [
                node_id for node_id in self.nodes if in_degree.get(node_id, 0) > 0
            ]
            raise CyclicDependencyError(unvisited)

    def get_root_nodes(self) -> list[str]:
        return [
            node_id for node_id, node in self.nodes.items() if not node.dependencies
        ]

    def get_dependents(self, node_id: str) -> set[str]:
        return self.adjacency.get(node_id, set())

    def get_dependencies(self, node_id: str) -> tuple[str, ...]:
        return self.nodes[node_id].dependencies

    def topological_sort(self) -> list[str]:
        in_degree = {node_id: len(deps) for node_id, deps in self.reverse_adjacency.items()}
        for node_id in self.nodes:
            if node_id not in in_degree:
                in_degree[node_id] = 0

        queue = sorted([node_id for node_id, degree in in_degree.items() if degree == 0])
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in sorted(self.adjacency.get(current, set())):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result
