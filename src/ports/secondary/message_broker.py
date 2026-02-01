from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TaskMessage:
    """
    Payload for a task dispatch event.
    
    Attributes:
        id (str): Unique message ID.
        execution_id (str): Trace ID for the workflow execution.
        node_id (str): The node to be executed.
        handler (str): Function identifier for the worker.
        config (dict): Resolved configuration parameters.
        stream_id (str | None): Internal Stream ID (assigned by Redis).
    """
    id: str
    execution_id: str
    node_id: str
    handler: str
    config: dict
    stream_id: str | None = None


@dataclass
class CompletionMessage:
    """
    Payload for a task completion event.

    Attributes:
        id (str): Unique message ID.
        execution_id (str): Trace ID.
        node_id (str): The node that completed.
        success (bool): Whether the execution succeeded.
        output (dict | None): Result data (if successful).
        error (str | None): Error message (if failed).
        stream_id (str | None): Internal Stream ID.
    """
    id: str
    execution_id: str
    node_id: str
    success: bool
    output: dict | None = None
    error: str | None = None
    stream_id: str | None = None


class IMessageBroker(ABC):
    """
    Interface for the Event Bus/Message Queue.
    
    Abstracts the underlying message streaming platform (e.g., Redis Streams).
    Supports Consumer Groups for parallel processing and reliability.
    """
    @abstractmethod
    async def publish_task(self, task: TaskMessage) -> str:
        """Publishes a task to the ready queue."""
        pass

    @abstractmethod
    async def publish_completion(self, completion: CompletionMessage) -> str:
        """Publishes a completion event to the results queue."""
        pass

    @abstractmethod
    async def consume_tasks(
        self, consumer_group: str, consumer_name: str, count: int = 1, block_ms: int = 5000
    ) -> list[TaskMessage]:
        """Consumes a batch of tasks as part of a consumer group."""
        pass

    @abstractmethod
    async def consume_completions(
        self, consumer_group: str, consumer_name: str, count: int = 10, block_ms: int = 1000
    ) -> list[CompletionMessage]:
        """Consumes completion events for the orchestrator."""
        pass

    @abstractmethod
    async def acknowledge_task(self, message_id: str) -> None:
        """Acknowledges successful processing of a task message."""
        pass

    @abstractmethod
    async def acknowledge_completion(self, message_id: str) -> None:
        """Acknowledges successful processing of a completion message."""
        pass

    @abstractmethod
    async def create_consumer_groups(self) -> None:
        """Idempotently initializes required consumer groups."""
        pass

    @abstractmethod
    async def claim_stalled_tasks(
        self, consumer_group: str, new_consumer: str, min_idle_ms: int = 300000, count: int = 10
    ) -> list[tuple[str, TaskMessage]]:
        """
        Recovers tasks that have arguably failed (stalled beyond min_idle_ms).
        Used by the Reaper for fault tolerance.
        """
        pass
