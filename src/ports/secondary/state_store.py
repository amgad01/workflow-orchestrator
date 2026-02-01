from abc import ABC, abstractmethod
from src.domain.workflow.value_objects.node_status import NodeStatus

class IStateStore(ABC):
    """
    Interface for the high-frequency 'Hot Path' state store (Redis).
    
    This component handles:
    1. Ephemeral node status updates (millisecond latency).
    2. Distributed locking for race condition prevention.
    3. Workflow execution metadata for rapid lookups.
    4. Data passing (storing intermediate node outputs).
    """
    @abstractmethod
    async def set_execution_metadata(self, execution_id: str, metadata: dict) -> None:
        """Stores immutable metadata (workflow_id, timeouts) for quick access."""
        pass

    @abstractmethod
    async def get_execution_metadata(self, execution_id: str) -> dict | None:
        """Retrieves execution metadata."""
        pass

    @abstractmethod
    async def set_execution_status(self, execution_id: str, status: NodeStatus) -> None:
        """Updates the overall status of the execution in the hot store."""
        pass

    @abstractmethod
    async def get_execution_status(self, execution_id: str) -> NodeStatus | None:
        """Retrieves the current execution status from the hot store."""
        pass

    @abstractmethod
    async def set_node_status(self, execution_id: str, node_id: str, status: NodeStatus) -> None:
        pass

    @abstractmethod
    async def get_node_status(self, execution_id: str, node_id: str) -> NodeStatus | None:
        pass

    @abstractmethod
    async def get_all_node_statuses(self, execution_id: str) -> dict[str, NodeStatus]:
        pass

    @abstractmethod
    async def set_node_output(self, execution_id: str, node_id: str, output: dict) -> None:
        pass

    @abstractmethod
    async def get_node_output(self, execution_id: str, node_id: str) -> dict | None:
        pass

    @abstractmethod
    async def get_all_outputs(self, execution_id: str) -> dict[str, dict]:
        pass

    @abstractmethod
    async def acquire_lock(self, key: str, ttl_seconds: int = 30) -> bool:
        """
        Acquires a distributed lock for strict concurrency control.
        Used to prevent race conditions during Fan-In evaluation.
        """
        pass

    @abstractmethod
    async def release_lock(self, key: str) -> None:
        """Releases a previously acquired distributed lock."""
        pass
