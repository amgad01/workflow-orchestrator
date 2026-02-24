import json

import redis.asyncio as redis

from src.ports.secondary.message_broker import (
    CompletionMessage,
    IMessageBroker,
    TaskMessage,
)
from src.shared.config import settings


class RedisMessageBroker(IMessageBroker):
    """Redis Streams implementation supporting consumer groups and at-least-once delivery."""

    TASK_STREAM = settings.STREAM_TASK_KEY
    COMPLETION_STREAM = settings.STREAM_COMPLETION_KEY
    TASK_GROUP = settings.STREAM_TASK_GROUP
    COMPLETION_GROUP = settings.STREAM_COMPLETION_GROUP

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def create_consumer_groups(self) -> None:
        for stream, group in [
            (self.TASK_STREAM, self.TASK_GROUP),
            (self.COMPLETION_STREAM, self.COMPLETION_GROUP),
        ]:
            try:
                await self._redis.xgroup_create(stream, group, id="0", mkstream=True)  # noqa: B007
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def publish_task(self, task: TaskMessage) -> str:
        message_id = await self._redis.xadd(
            self.TASK_STREAM,
            {
                "id": task.id,
                "execution_id": task.execution_id,
                "node_id": task.node_id,
                "handler": task.handler,
                "config": json.dumps(task.config),
            },
        )
        return message_id

    async def publish_completion(self, completion: CompletionMessage) -> str:
        message_id = await self._redis.xadd(
            self.COMPLETION_STREAM,
            {
                "id": completion.id,
                "execution_id": completion.execution_id,
                "node_id": completion.node_id,
                "success": "1" if completion.success else "0",
                "output": json.dumps(completion.output) if completion.output else "",
                "error": completion.error or "",
            },
        )
        return message_id

    async def consume_tasks(
        self, consumer_group: str, consumer_name: str, count: int = 1, block_ms: int = 5000
    ) -> list[TaskMessage]:
        try:
            messages = await self._redis.xreadgroup(
                consumer_group or self.TASK_GROUP,
                consumer_name,
                {self.TASK_STREAM: ">"},
                count=count,
                block=block_ms,
            )
        except redis.ResponseError as e:
            if "NOGROUP" in str(e):
                await self.create_consumer_groups()
                return []
            raise

        tasks = []
        if messages:
            for _stream, stream_messages in messages:
                for message_id, data in stream_messages:
                    tasks.append(
                        TaskMessage(
                            id=data["id"],
                            execution_id=data["execution_id"],
                            node_id=data["node_id"],
                            handler=data["handler"],
                            config=json.loads(data["config"]),
                            stream_id=message_id,
                        )
                    )
        return tasks

    async def consume_completions(
        self, consumer_group: str, consumer_name: str, count: int = 10, block_ms: int = 1000
    ) -> list[CompletionMessage]:
        try:
            messages = await self._redis.xreadgroup(
                consumer_group or self.COMPLETION_GROUP,
                consumer_name,
                {self.COMPLETION_STREAM: ">"},
                count=count,
                block=block_ms,
            )
        except redis.ResponseError as e:
            if "NOGROUP" in str(e):
                await self.create_consumer_groups()
                return []
            raise

        completions = []
        if messages:
            for _stream, stream_messages in messages:
                for message_id, data in stream_messages:
                    completions.append(
                        CompletionMessage(
                            id=data["id"],
                            execution_id=data["execution_id"],
                            node_id=data["node_id"],
                            success=data["success"] == "1",
                            output=json.loads(data["output"]) if data.get("output") else None,
                            error=data.get("error") or None,
                            stream_id=message_id,
                        )
                    )
        return completions

    async def acknowledge_task(self, message_id: str) -> None:
        await self._redis.xack(self.TASK_STREAM, self.TASK_GROUP, message_id)

    async def acknowledge_completion(self, message_id: str) -> None:
        await self._redis.xack(self.COMPLETION_STREAM, self.COMPLETION_GROUP, message_id)

    async def claim_stalled_tasks(
        self, consumer_group: str, new_consumer: str, min_idle_ms: int = 300000, count: int = 10
    ) -> list[tuple[str, TaskMessage]]:
        try:
            response = await self._redis.xautoclaim(
                self.TASK_STREAM,
                consumer_group,
                new_consumer,
                min_idle_time=min_idle_ms,
                start_id="0-0",
                count=count,
            )
            claimed_messages = response[1]
        except redis.ResponseError as e:
            if "NOGROUP" in str(e):
                return []
            raise

        tasks = []
        if claimed_messages:
            for message_id, data in claimed_messages:
                if not data:
                    continue

                task = TaskMessage(
                    id=data["id"],
                    execution_id=data["execution_id"],
                    node_id=data["node_id"],
                    handler=data["handler"],
                    config=json.loads(data["config"]),
                    stream_id=message_id,
                )
                tasks.append((message_id, task))
        return tasks
