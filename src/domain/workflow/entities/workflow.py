from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class Node:
    """
    Represents a single step in a workflow DAG.

    Attributes:
        id (str): Unique identifier for the node within the DAG.
        handler (str): The identifier of the task handler to execute (e.g., "call_llm").
        dependencies (tuple[str, ...]): List of node IDs that must complete before this node can start.
        config (dict): Configuration parameters passed to the handler.
        condition (str | None): Optional conditional expression to evaluate before execution.
    """

    id: str
    handler: str
    dependencies: tuple[str, ...]
    config: dict = field(default_factory=dict)
    condition: str | None = None


@dataclass
class Workflow:
    """
    Root aggregate for a workflow definition.

    Attributes:
        name (str): Human-readable name of the workflow.
        dag_json (dict): The raw JSON definition of the DAG structure.
        id (str): Unique identifier (UUID4).
        created_at (datetime): Timestamp when the workflow was submitted.
    """

    name: str
    dag_json: dict
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
