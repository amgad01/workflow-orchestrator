import asyncio
import signal
from datetime import datetime, timezone
from uuid import uuid4

from src.adapters.secondary.redis.redis_dlq_repository import RedisDLQRepository
from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.adapters.secondary.redis.redis_state_store import RedisStateStore
from src.adapters.secondary.workers.base_worker import BaseWorker
from src.adapters.secondary.workers.external_service_worker import ExternalServiceWorker
from src.adapters.secondary.workers.io_workers import InputWorker, OutputWorker
from src.adapters.secondary.workers.llm_service_worker import LLMServiceWorker
from src.adapters.secondary.workers.decision_worker import DecisionWorker
from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry
from src.ports.secondary.message_broker import CompletionMessage, TaskMessage
from src.shared.metrics import metrics_registry
from src.shared.redis_client import redis_client
from src.shared.config import settings
from src.shared.logger import get_logger

logger = get_logger(__name__)


class WorkerRunner:
    """
    Main entry point for the Worker process.
    
    This component consumes tasks from Redis Streams, delegates them to specific
    handler implementations (e.g. LLM, API), and reports results.
    
    Key Responsibilities:
    - Task Consumption (Group-based).
    - Idempotency (prevent double-processing).
    - Resilience (DLQ management and retries).
    """
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
                    # Process tasks in parallel for high throughput
                    await asyncio.gather(*[self.process_task(t) for t in tasks])

            except Exception as e:
                logger.error("worker_main_loop_error", error=str(e), exc_info=True)
                if not shutdown_event.is_set():
                    await asyncio.sleep(1)
        
        logger.info("worker_shutdown_complete")

    async def process_task(self, task: TaskMessage) -> None:
        """
        Executes a single task with full resilience wrappers.
        
        Business Logic:
        1. Idempotency Check: Verifies if task ID was already processed (Redis Set).
        2. Execution: Delegates to the registered handler.
        3. Failure Handling: 
            - Retries locally if below max limit.
            - Moves to Dead Letter Queue (DLQ) if retries exhausted.
        4. Completion: Publishes success/failure event to Orchestrator.
        """
        from src.shared.logger import bind_context, clear_context
        bind_context({"execution_id": task.execution_id, "node_id": task.node_id})
        
        try:
            processed_key = f"execution:{task.execution_id}:processed_tasks"
            is_processed = await redis_client.sismember(processed_key, task.id)
            
            if is_processed:
                logger.info("skipping_duplicate_task", task_id=task.id)
                if task.stream_id:
                    await self._broker.acknowledge_task(task.stream_id)
                return

            logger.info("processing_task", handler=task.handler)

            handler = self._handlers.get(task.handler)
            if not handler:
                logger.error("handler_not_found", handler=task.handler)
                return

            import time
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
                
                # DLQ retry tracking
                if settings.DLQ_ENABLED:
                    retry_count = await self._increment_retry_count(task)
                    
                    if retry_count >= settings.DLQ_MAX_RETRIES:
                        await self._move_to_dlq(task, str(e), retry_count)
                        logger.warning("task_moved_to_dlq", retry_count=retry_count)
                        # Only send failure to orchestrator AFTER max retries
                        completion = CompletionMessage(
                            id=task.id,
                            execution_id=task.execution_id,
                            node_id=task.node_id,
                            success=False,
                            error=str(e),
                        )
                    else:
                        logger.info("task_failure_retry", retry_count=retry_count, max_retries=settings.DLQ_MAX_RETRIES)
                        # Re-publish task for another attempt
                        await self._broker.publish_task(task)
                        # Mark current stream message as processed, BUT DO NOT send completion to orchestrator
                        # so the node remains in RUNNING/PENDING state from his perspective.
                        if task.stream_id:
                            await self._broker.acknowledge_task(task.stream_id)
                        return
                else:
                    # DLQ disabled, fail immediately
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
            
            await redis_client.sadd(processed_key, task.id)
            await redis_client.expire(processed_key, 86400)
            
            if task.stream_id:
                await self._broker.acknowledge_task(task.stream_id)
        finally:
            clear_context()

    async def _increment_retry_count(self, task: TaskMessage) -> int:
        """Increment retry count and apply exponential backoff delay."""
        retry_key = f"task_retry:{task.execution_id}:{task.node_id}"
        retry_count = await redis_client.incr(retry_key)
        await redis_client.expire(retry_key, 86400)  # 24h TTL
        
        # Apply exponential backoff with jitter before retry
        backoff_delay = self._calculate_backoff_delay(retry_count)
        if backoff_delay > 0:
            logger.info("applying_retry_backoff", delay_seconds=backoff_delay, retry_count=retry_count)
            await asyncio.sleep(backoff_delay)
        
        return retry_count

    def _calculate_backoff_delay(self, retry_count: int) -> float:
        """
        Calculate exponential backoff delay with jitter.
        
        Formula: min(base * 2^retry_count, max_delay) + random_jitter
        This prevents thundering herd when multiple tasks retry simultaneously.
        """
        import random
        base_delay = 1.0  # 1 second base
        max_delay = 30.0  # Cap at 30 seconds
        
        exponential_delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
        jitter = random.uniform(0, exponential_delay * 0.1)  # 10% jitter
        
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
