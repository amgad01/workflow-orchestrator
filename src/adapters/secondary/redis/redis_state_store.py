import json
import redis.asyncio as redis
from src.domain.workflow.value_objects.node_status import NodeStatus
from src.ports.secondary.state_store import IStateStore

class RedisStateStore(IStateStore):
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    def _status_key(self, execution_id: str) -> str:
        return f"execution:{execution_id}:status"

    def _output_key(self, execution_id: str) -> str:
        return f"execution:{execution_id}:output"

    def _execution_metadata_key(self, execution_id: str) -> str:
        return f"execution:{execution_id}:metadata"

    def _execution_status_key(self, execution_id: str) -> str:
        return f"execution:{execution_id}:aggregate_status"

    async def set_node_status(self, execution_id: str, node_id: str, status: NodeStatus) -> None:
        await self._redis.hset(self._status_key(execution_id), node_id, status.value)

    async def get_node_status(self, execution_id: str, node_id: str) -> NodeStatus | None:
        value = await self._redis.hget(self._status_key(execution_id), node_id)
        if value:
            val = value.decode() if isinstance(value, bytes) else value
            return NodeStatus(val)
        return None

    async def get_all_node_statuses(self, execution_id: str) -> dict[str, NodeStatus]:
        data = await self._redis.hgetall(self._status_key(execution_id))
        result = {}
        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            result[key] = NodeStatus(val)
        return result

    async def set_node_output(self, execution_id: str, node_id: str, output: dict) -> None:
        await self._redis.hset(self._output_key(execution_id), node_id, json.dumps(output))

    async def get_node_output(self, execution_id: str, node_id: str) -> dict | None:
        value = await self._redis.hget(self._output_key(execution_id), node_id)
        if value:
            val = value.decode() if isinstance(value, bytes) else value
            return json.loads(val)
        return None

    async def get_all_outputs(self, execution_id: str) -> dict[str, dict]:
        data = await self._redis.hgetall(self._output_key(execution_id))
        result = {}
        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            result[key] = json.loads(val)
        return result

    async def acquire_lock(self, key: str, ttl_seconds: int = 30) -> bool:
        return await self._redis.set(f"lock:{key}", "1", nx=True, ex=ttl_seconds)

    async def release_lock(self, key: str) -> None:
        await self._redis.delete(f"lock:{key}")

    async def set_execution_metadata(self, execution_id: str, metadata: dict) -> None:
        await self._redis.set(self._execution_metadata_key(execution_id), json.dumps(metadata), ex=86400)

    async def get_execution_metadata(self, execution_id: str) -> dict | None:
        value = await self._redis.get(self._execution_metadata_key(execution_id))
        if value:
            val = value.decode() if isinstance(value, bytes) else value
            return json.loads(val)
        return None

    async def set_execution_status(self, execution_id: str, status: NodeStatus) -> None:
        await self._redis.set(self._execution_status_key(execution_id), status.value, ex=86400)

    async def get_execution_status(self, execution_id: str) -> NodeStatus | None:
        value = await self._redis.get(self._execution_status_key(execution_id))
        if value:
            val = value.decode() if isinstance(value, bytes) else value
            return NodeStatus(val)
        return None
