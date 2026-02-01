from abc import ABC, abstractmethod
from typing import Optional

from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry


class IDLQRepository(ABC):
    @abstractmethod
    async def push(self, entry: DeadLetterEntry) -> None:
        pass

    @abstractmethod
    async def pop(self, entry_id: str) -> Optional[DeadLetterEntry]:
        pass

    @abstractmethod
    async def list_entries(self, limit: int = 100) -> list[DeadLetterEntry]:
        pass

    @abstractmethod
    async def count(self) -> int:
        pass

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        pass
