from abc import ABC, abstractmethod

from src.ports.secondary.message_broker import TaskMessage


class BaseWorker(ABC):
    @property
    @abstractmethod
    def handler_name(self) -> str:
        pass

    @abstractmethod
    async def process(self, task: TaskMessage) -> dict:
        pass
