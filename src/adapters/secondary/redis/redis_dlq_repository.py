import json
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry
from src.ports.secondary.dlq_repository import IDLQRepository


class RedisDLQRepository(IDLQRepository):
    DLQ_STREAM = "workflow:dlq"
    DLQ_INDEX = "workflow:dlq:index"

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def push(self, entry: DeadLetterEntry) -> None:
        await self._redis.xadd(
            self.DLQ_STREAM,
            {
                "id": entry.id,
                "data": json.dumps(entry.to_dict()),
            },
        )
        await self._redis.hset(self.DLQ_INDEX, entry.id, "1")

    async def pop(self, entry_id: str) -> Optional[DeadLetterEntry]:
        entries = await self.list_entries(limit=1000)
        for entry in entries:
            if entry.id == entry_id:
                await self.delete(entry_id)
                return entry
        return None

    async def list_entries(self, limit: int = 100) -> list[DeadLetterEntry]:
        messages = await self._redis.xrange(self.DLQ_STREAM, count=limit)
        entries = []
        for stream_id, data in messages:
            try:
                entry_dict = json.loads(data["data"])
                entries.append(DeadLetterEntry.from_dict(entry_dict))
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    async def count(self) -> int:
        length = await self._redis.xlen(self.DLQ_STREAM)
        return length

    async def delete(self, entry_id: str) -> bool:
        messages = await self._redis.xrange(self.DLQ_STREAM, count=1000)
        for stream_id, data in messages:
            if data.get("id") == entry_id:
                await self._redis.xdel(self.DLQ_STREAM, stream_id)
                await self._redis.hdel(self.DLQ_INDEX, entry_id)
                return True
        return False
