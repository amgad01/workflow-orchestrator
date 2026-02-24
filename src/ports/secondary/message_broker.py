from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TaskMessage:
    id: str
    execution_id: str
    node_id: str
    handler: str
    config: dict
    stream_id: str | None = None


@dataclass
class CompletionMessage:
    id: str
    execution_id: str
    node_id: str
    success: bool
    output: dict | None = None
    error: str | None = None
    stream_id: str | None = None


class IMessageBroker(ABC):
    """Interface for the event bus / message queue (e.g. Redis Streams)."""

    @abstractmethod
    async def publish_task(self, task: TaskMessage) -> str:
        pass

    @abstractmethod
    async def publish_completion(self, completion: CompletionMessage) -> str:
        pass

    @abstractmethod
    async def consume_tasks(
        self, consumer_group: str, consumer_name: str, count: int = 1, block_ms: int = 5000
    ) -> list[TaskMessage]:
        pass

    @abstractmethod
    async def consume_completions(
        self, consumer_group: str, consumer_name: str, count: int = 10, block_ms: int = 1000
    ) -> list[CompletionMessage]:
        pass

    @abstractmethod
    async def acknowledge_task(self, message_id: str) -> None:
        pass

    @abstractmethod
    async def acknowledge_completion(self, message_id: str) -> None:
        pass

    @abstractmethod
    async def create_consumer_groups(self) -> None:
        pass

    @abstractmethod
    async def claim_stalled_tasks(
        self, consumer_group: str, new_consumer: str, min_idle_ms: int = 300000, count: int = 10
    ) -> list[tuple[str, TaskMessage]]:
        pass
