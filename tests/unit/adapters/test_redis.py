import json
from unittest.mock import AsyncMock

import pytest

from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.adapters.secondary.redis.redis_state_store import RedisStateStore
from src.domain.workflow.value_objects.node_status import NodeStatus
from src.ports.secondary.message_broker import CompletionMessage, TaskMessage


@pytest.mark.asyncio
async def test_redis_message_broker_publish_task():
    mock_redis = AsyncMock()
    broker = RedisMessageBroker(mock_redis)

    task = TaskMessage(
        id="t1", execution_id="e1", node_id="n1", handler="h1", config={"key": "val"}
    )

    await broker.publish_task(task)

    # Check xadd call
    mock_redis.xadd.assert_called_once()
    args, kwargs = mock_redis.xadd.call_args
    assert args[0] == RedisMessageBroker.TASK_STREAM
    assert args[1]["id"] == "t1"
    assert json.loads(args[1]["config"]) == {"key": "val"}


@pytest.mark.asyncio
async def test_redis_message_broker_publish_completion():
    mock_redis = AsyncMock()
    broker = RedisMessageBroker(mock_redis)

    completion = CompletionMessage(
        id="t1", execution_id="e1", node_id="n1", success=True, output={"res": "ok"}
    )

    await broker.publish_completion(completion)
    mock_redis.xadd.assert_called_once()
    args, kwargs = mock_redis.xadd.call_args
    assert args[0] == RedisMessageBroker.COMPLETION_STREAM
    assert args[1]["success"] == "1"


@pytest.mark.asyncio
async def test_redis_message_broker_consume_tasks():
    mock_redis = AsyncMock()
    broker = RedisMessageBroker(mock_redis)

    # Mock xreadgroup reply
    mock_redis.xreadgroup.return_value = [
        (
            RedisMessageBroker.TASK_STREAM,
            [
                (
                    "msg-1",
                    {
                        "id": "t1",
                        "execution_id": "e1",
                        "node_id": "n1",
                        "handler": "h1",
                        "config": json.dumps({"key": "val"}),
                    },
                )
            ],
        )
    ]

    tasks = await broker.consume_tasks("group", "consumer")
    assert len(tasks) == 1
    assert tasks[0].id == "t1"
    assert tasks[0].config == {"key": "val"}


@pytest.mark.asyncio
async def test_redis_message_broker_consume_completions():
    mock_redis = AsyncMock()
    broker = RedisMessageBroker(mock_redis)

    # Mock xreadgroup reply
    mock_redis.xreadgroup.return_value = [
        (
            RedisMessageBroker.COMPLETION_STREAM,
            [
                (
                    "msg-1",
                    {
                        "id": "t1",
                        "execution_id": "e1",
                        "node_id": "n1",
                        "success": "1",
                        "output": json.dumps({"res": "ok"}),
                        "error": "",
                    },
                )
            ],
        )
    ]

    completions = await broker.consume_completions("group", "consumer")
    assert len(completions) == 1
    assert completions[0].success is True
    assert completions[0].output == {"res": "ok"}


@pytest.mark.asyncio
async def test_redis_message_broker_acknowledge():
    mock_redis = AsyncMock()
    broker = RedisMessageBroker(mock_redis)
    await broker.acknowledge_task("msg-1")
    mock_redis.xack.assert_called_with(
        RedisMessageBroker.TASK_STREAM, RedisMessageBroker.TASK_GROUP, "msg-1"
    )

    await broker.acknowledge_completion("msg-2")
    mock_redis.xack.assert_called_with(
        RedisMessageBroker.COMPLETION_STREAM, RedisMessageBroker.COMPLETION_GROUP, "msg-2"
    )


@pytest.mark.asyncio
async def test_redis_message_broker_claim_stalled():
    mock_redis = AsyncMock()
    broker = RedisMessageBroker(mock_redis)

    # Mock xautoclaim response: (next_id, [ (id, data), ... ])
    mock_redis.xautoclaim.return_value = (
        "0-0",
        [
            (
                "msg-1",
                {
                    "id": "t1",
                    "execution_id": "e1",
                    "node_id": "n1",
                    "handler": "h1",
                    "config": json.dumps({"key": "val"}),
                },
            )
        ],
    )

    tasks = await broker.claim_stalled_tasks("group", "consumer")
    assert len(tasks) == 1
    assert tasks[0][0] == "msg-1"
    assert tasks[0][1].id == "t1"


@pytest.mark.asyncio
async def test_redis_state_store_node_status():
    mock_redis = AsyncMock()
    store = RedisStateStore(mock_redis)

    await store.set_node_status("e1", "n1", NodeStatus.RUNNING)
    mock_redis.hset.assert_called_with("execution:e1:status", "n1", "RUNNING")

    mock_redis.hget.return_value = b"RUNNING"
    status = await store.get_node_status("e1", "n1")
    assert status == NodeStatus.RUNNING


@pytest.mark.asyncio
async def test_redis_state_store_complex_gets():
    mock_redis = AsyncMock()
    store = RedisStateStore(mock_redis)

    # get_all_node_statuses
    mock_redis.hgetall.return_value = {b"n1": b"RUNNING", b"n2": b"COMPLETED"}
    statuses = await store.get_all_node_statuses("e1")
    assert statuses["n1"] == NodeStatus.RUNNING
    assert statuses["n2"] == NodeStatus.COMPLETED

    # get_all_outputs
    mock_redis.hgetall.return_value = {b"n1": json.dumps({"a": 1}).encode()}
    outputs = await store.get_all_outputs("e1")
    assert outputs["n1"] == {"a": 1}


@pytest.mark.asyncio
async def test_redis_state_store_locking():
    mock_redis = AsyncMock()
    store = RedisStateStore(mock_redis)

    mock_redis.set.return_value = True
    locked = await store.acquire_lock("k1")
    assert locked is True
    mock_redis.set.assert_called_with("lock:k1", "1", nx=True, ex=30)

    await store.release_lock("k1")
    mock_redis.delete.assert_called_with("lock:k1")


@pytest.mark.asyncio
async def test_redis_state_store_metadata():
    mock_redis = AsyncMock()
    store = RedisStateStore(mock_redis)

    await store.set_execution_metadata("e1", {"wf": "123"})
    mock_redis.set.assert_called_with("execution:e1:metadata", json.dumps({"wf": "123"}), ex=86400)

    mock_redis.get.return_value = json.dumps({"wf": "123"}).encode()
    meta = await store.get_execution_metadata("e1")
    assert meta == {"wf": "123"}


@pytest.mark.asyncio
async def test_redis_state_store_execution_status():
    mock_redis = AsyncMock()
    store = RedisStateStore(mock_redis)

    await store.set_execution_status("e1", NodeStatus.COMPLETED)
    mock_redis.set.assert_called_with("execution:e1:aggregate_status", "COMPLETED", ex=86400)

    mock_redis.get.return_value = b"COMPLETED"
    status = await store.get_execution_status("e1")
    assert status == NodeStatus.COMPLETED


@pytest.mark.asyncio
async def test_create_consumer_groups():
    m_redis = AsyncMock()
    broker = RedisMessageBroker(m_redis)
    await broker.create_consumer_groups()
    assert m_redis.xgroup_create.called


@pytest.mark.asyncio
async def test_consume_tasks_nogroup():
    m_redis = AsyncMock()
    broker = RedisMessageBroker(m_redis)
    from redis import ResponseError

    m_redis.xreadgroup.side_effect = ResponseError("NOGROUP No such key")

    tasks = await broker.consume_tasks("group", "consumer")
    assert tasks == []
    assert m_redis.xgroup_create.called
