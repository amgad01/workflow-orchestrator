from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.adapters.primary.api.dependencies import get_message_broker, get_state_store
from src.adapters.secondary.redis.redis_dlq_repository import RedisDLQRepository
from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.adapters.secondary.redis.redis_state_store import RedisStateStore
from src.domain.workflow.value_objects.node_status import NodeStatus
from src.ports.secondary.message_broker import TaskMessage
from src.shared.logger import get_logger
from src.shared.redis_client import redis_client

logger = get_logger(__name__)

# API versioning for forward compatibility
API_VERSION = "v1"
router = APIRouter(prefix=f"/api/{API_VERSION}/admin/dlq", tags=["Admin - Dead Letter Queue"])


# Lazy helper since DLQ repo isn't in standard DI
def get_dlq_repository() -> RedisDLQRepository:
    return RedisDLQRepository(redis_client)


class DLQEntryResponse(BaseModel):
    id: str
    task_id: str
    execution_id: str
    node_id: str
    handler: str
    error_message: str
    retry_count: int
    original_timestamp: str
    failed_at: str


class DLQListResponse(BaseModel):
    entries: list[DLQEntryResponse]
    count: int


class DLQRetryResponse(BaseModel):
    status: str
    message: str
    task_id: str


# Routes will use Depends()


@router.get(
    "",
    response_model=DLQListResponse,
    summary="List Dead Letter Queue entries",
    description="Retrieve all tasks that have failed after max retries.",
)
async def list_dlq_entries(
    limit: int = 100,
    dlq_repository: RedisDLQRepository = Depends(get_dlq_repository),
) -> DLQListResponse:
    entries = await dlq_repository.list_entries(limit=limit)
    count = await dlq_repository.count()

    return DLQListResponse(
        entries=[
            DLQEntryResponse(
                id=e.id,
                task_id=e.task_id,
                execution_id=e.execution_id,
                node_id=e.node_id,
                handler=e.handler,
                error_message=e.error_message,
                retry_count=e.retry_count,
                original_timestamp=e.original_timestamp.isoformat(),
                failed_at=e.failed_at.isoformat(),
            )
            for e in entries
        ],
        count=count,
    )


@router.post(
    "/{entry_id}/retry",
    response_model=DLQRetryResponse,
    summary="Retry a Dead Letter Queue entry",
    description="Remove entry from DLQ and re-submit the task for processing.",
)
async def retry_dlq_entry(
    entry_id: str,
    dlq_repository: RedisDLQRepository = Depends(get_dlq_repository),
    message_broker: RedisMessageBroker = Depends(get_message_broker),
    state_store: RedisStateStore = Depends(get_state_store),
) -> DLQRetryResponse:
    entry = await dlq_repository.pop(entry_id)

    if not entry:
        raise HTTPException(status_code=404, detail=f"DLQ entry {entry_id} not found")

    task = TaskMessage(
        id=entry.task_id,
        execution_id=entry.execution_id,
        node_id=entry.node_id,
        handler=entry.handler,
        config=entry.config,
    )

    # Reset workflow status to RUNNING in state store (Hot Path)
    await state_store.set_execution_status(entry.execution_id, NodeStatus.RUNNING)

    # Also reset the node status to RUNNING
    await state_store.set_node_status(entry.execution_id, entry.node_id, NodeStatus.RUNNING)

    await message_broker.publish_task(task)

    # Clear the retry counter to give it fresh attempts
    retry_key = f"task_retry:{entry.execution_id}:{entry.node_id}"
    await redis_client.delete(retry_key)

    logger.info(f"Retried DLQ entry {entry_id} as task {task.id}, reset status to RUNNING")

    return DLQRetryResponse(
        status="success",
        message="Task re-submitted to queue",
        task_id=entry.task_id,
    )


@router.delete(
    "/{entry_id}",
    summary="Delete a Dead Letter Queue entry",
    description="Permanently remove an entry from the DLQ without retrying.",
)
async def delete_dlq_entry(
    entry_id: str,
    dlq_repository: RedisDLQRepository = Depends(get_dlq_repository),
):
    deleted = await dlq_repository.delete(entry_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"DLQ entry {entry_id} not found")

    logger.info(f"Deleted DLQ entry {entry_id}")

    return {"status": "success", "message": f"DLQ entry {entry_id} deleted"}
