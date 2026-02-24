import asyncio
import random
import signal
import time
from datetime import datetime, timezone
from uuid import uuid4

from src.adapters.secondary.redis.redis_dlq_repository import RedisDLQRepository
from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.adapters.secondary.redis.redis_state_store import RedisStateStore
from src.adapters.secondary.workers.base_worker import BaseWorker
from src.adapters.secondary.workers.decision_worker import DecisionWorker
from src.adapters.secondary.workers.external_service_worker import ExternalServiceWorker
from src.adapters.secondary.workers.io_workers import InputWorker, OutputWorker
from src.adapters.secondary.workers.llm_service_worker import LLMServiceWorker
from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry
from src.ports.secondary.message_broker import CompletionMessage, TaskMessage
from src.shared.config import settings
from src.shared.logger import get_logger
from src.shared.metrics import metrics_registry
from src.shared.redis_client import redis_client

logger = get_logger(__name__)


class WorkerRunner:
    """Consumes tasks from Redis Streams, delegates to handlers, and reports results."""

    def __init__(self):
        self._broker = RedisMessageBroker(redis_client)
        self._state_store = RedisStateStore(redis_client)
        self._dlq_repository = RedisDLQRepository(redis_client)
        self._consumer_name = f"worker-{uuid4().hex[:8]}"
        self._handlers: dict[str, BaseWorker] = {}

    def register_handler(self, worker: BaseWorker) -> None:
        self._handlers[worker.handler_name] = worker

    async def run(self) -> None:
        logger.info("worker_starting", consumer_name=self._consumer_name, delays_enabled=settings.WORKER_ENABLE_DELAYS)
        await self._broker.create_consumer_groups()

        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def signal_handler():
            logger.info("shutdown_signal_received")
            shutdown_event.set()

        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

        while not shutdown_event.is_set():
            try:
                tasks = await self._broker.consume_tasks(
                    consumer_group=RedisMessageBroker.TASK_GROUP,
                    consumer_name=self._consumer_name,
                    count=settings.WORKER_BATCH_SIZE,
                    block_ms=settings.WORKER_BLOCK_MS,
                )
                if tasks:
                    await asyncio.gather(*[self.process_task(t) for t in tasks])
            except Exception as e:
                logger.error("worker_main_loop_error", error=str(e), exc_info=True)
                if not shutdown_event.is_set():
                    await asyncio.sleep(settings.WORKER_ERROR_PAUSE_SECONDS)

        logger.info("worker_shutdown_complete")

    async def process_task(self, task: TaskMessage) -> None:
        """Execute a task with idempotency checks, retries, and DLQ fallback."""
        from src.shared.logger import bind_context, clear_context
        bind_context({"execution_id": task.execution_id, "node_id": task.node_id})

        try:
            # Idempotency: skip if already processed
            processed_key = f"execution:{task.execution_id}:processed_tasks"
            if await redis_client.sismember(processed_key, task.id):
                logger.info("skipping_duplicate_task", task_id=task.id)
                if task.stream_id:
                    await self._broker.acknowledge_task(task.stream_id)
                return

            logger.info("processing_task", handler=task.handler)

            handler = self._handlers.get(task.handler)
            if not handler:
                logger.error("handler_not_found", handler=task.handler)
                return

            start_time = time.time()
            status = "SUCCESS"

            try:
                output = await handler.process(task)
                completion = CompletionMessage(
                    id=task.id,
                    execution_id=task.execution_id,
                    node_id=task.node_id,
                    success=True,
                    output=output,
                )
            except Exception as e:
                logger.error("task_failed", error=str(e), exc_info=True)
                status = "FAILED"

                if settings.DLQ_ENABLED:
                    retry_count = await self._increment_retry_count(task)

                    if retry_count >= settings.DLQ_MAX_RETRIES:
                        await self._move_to_dlq(task, str(e), retry_count)
                        logger.warning("task_moved_to_dlq", retry_count=retry_count)
                        completion = CompletionMessage(
                            id=task.id,
                            execution_id=task.execution_id,
                            node_id=task.node_id,
                            success=False,
                            error=str(e),
                        )
                    else:
                        # Re-publish for retry; don't notify orchestrator yet
                        logger.info("task_failure_retry", retry_count=retry_count, max_retries=settings.DLQ_MAX_RETRIES)
                        await self._broker.publish_task(task)
                        if task.stream_id:
                            await self._broker.acknowledge_task(task.stream_id)
                        return
                else:
                    completion = CompletionMessage(
                        id=task.id,
                        execution_id=task.execution_id,
                        node_id=task.node_id,
                        success=False,
                        error=str(e),
                    )

            duration = time.time() - start_time
            metrics_registry.record_node_completion(task.handler, status, duration)

            await self._broker.publish_completion(completion)

            # Mark as processed for idempotency
            await redis_client.sadd(processed_key, task.id)
            await redis_client.expire(processed_key, settings.WORKER_IDEMPOTENCY_TTL_SECONDS)

            if task.stream_id:
                await self._broker.acknowledge_task(task.stream_id)
        finally:
            clear_context()

    async def _increment_retry_count(self, task: TaskMessage) -> int:
        """Atomically increment retry counter and apply exponential backoff."""
        retry_key = f"task_retry:{task.execution_id}:{task.node_id}"
        retry_count = await redis_client.incr(retry_key)
        await redis_client.expire(retry_key, settings.WORKER_IDEMPOTENCY_TTL_SECONDS)

        backoff_delay = self._calculate_backoff_delay(retry_count)
        if backoff_delay > 0:
            logger.info("applying_retry_backoff", delay_seconds=backoff_delay, retry_count=retry_count)
            await asyncio.sleep(backoff_delay)

        return retry_count

    def _calculate_backoff_delay(self, retry_count: int) -> float:
        """min(base * 2^retry, max) + jitter"""
        base_delay = settings.WORKER_BACKOFF_BASE_SECONDS
        max_delay = settings.WORKER_BACKOFF_MAX_SECONDS

        exponential_delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
        jitter = random.uniform(0, exponential_delay * settings.WORKER_BACKOFF_JITTER_MAX)

        return exponential_delay + jitter

    async def _move_to_dlq(self, task: TaskMessage, error: str, retry_count: int) -> None:
        entry = DeadLetterEntry(
            task_id=task.id,
            execution_id=task.execution_id,
            node_id=task.node_id,
            handler=task.handler,
            config=task.config,
            error_message=error,
            retry_count=retry_count,
            original_timestamp=datetime.now(timezone.utc),
        )
        await self._dlq_repository.push(entry)


async def main():
    runner = WorkerRunner()
    runner.register_handler(InputWorker())
    runner.register_handler(OutputWorker())
    runner.register_handler(ExternalServiceWorker())
    runner.register_handler(LLMServiceWorker())
    runner.register_handler(DecisionWorker())
    await runner.run()


if __name__ == "__main__":
    from src.shared.logger import configure_logging
    configure_logging()
    asyncio.run(main())
