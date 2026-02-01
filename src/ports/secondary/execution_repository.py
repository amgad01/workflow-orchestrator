from abc import ABC, abstractmethod

from src.domain.workflow.entities.execution import Execution


class IExecutionRepository(ABC):
    """
    Interface for long-term persistence of Workflow Executions.
    
    This repository manages the 'Cold Path' storage (PostgreSQL), dealing with
    ACID-compliant records of workflow lifecycles, audit trails, and final states.
    It is NOT responsible for high-frequency node state updates (see IStateStore).
    """
    @abstractmethod
    async def save(self, execution: Execution) -> None:
        """Persists a new execution record."""
        pass

    @abstractmethod
    async def get_by_id(self, execution_id: str) -> Execution | None:
        """Retrieves a full execution aggregate by its ID."""
        pass

    @abstractmethod
    async def update(self, execution: Execution) -> None:
        """Updates the top-level status and timestamps of an execution."""
        pass

    @abstractmethod
    async def get_running_executions(self) -> list[Execution]:
        """Retrieves all executions currently in RUNNING state (for timeout checks)."""
        pass
