from abc import ABC, abstractmethod

from src.domain.workflow.entities.workflow import Workflow


class IWorkflowRepository(ABC):
    """
    Interface for persistence of Workflow Definitions.

    Manages the storage and retrieval of immutable DAG structures and configuration.
    """

    @abstractmethod
    async def save(self, workflow: Workflow) -> None:
        """Persists a new workflow definition."""
        pass

    @abstractmethod
    async def get_by_id(self, workflow_id: str) -> Workflow | None:
        """Retrieves a workflow definition by its unique ID."""
        pass
