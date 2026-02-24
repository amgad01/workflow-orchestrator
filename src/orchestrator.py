import asyncio
import contextlib
import signal
from uuid import uuid4

from src.adapters.secondary.persistence.pg_execution_repository import PostgresExecutionRepository
from src.adapters.secondary.persistence.pg_workflow_repository import PostgresWorkflowRepository
from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.adapters.secondary.redis.redis_state_store import RedisStateStore
from src.application.workflow.use_cases.orchestrate import OrchestrateUseCase
from src.ports.secondary.message_broker import CompletionMessage
from src.shared.config import settings
from src.shared.database import async_session_factory
from src.shared.logger import get_logger
from src.shared.metrics import metrics_registry
from src.shared.redis_client import redis_client

logger = get_logger(__name__)


class OrchestratorRunner:
    """Consumes completion events from Redis Streams and drives DAG progression."""

    def __init__(self):
        self._broker = RedisMessageBroker(redis_client)
        self._state_store = RedisStateStore(redis_client)
        self._consumer_name = f"orchestrator-{uuid4().hex[:8]}"

    async def run(self) -> None:
        logger.info("orchestrator_starting", consumer_name=self._consumer_name)
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

        async def timeout_checker():
            """Periodically scans running executions for timeouts."""
            while not shutdown_event.is_set():
                try:
                    async with async_session_factory() as session:
                        use_case = OrchestrateUseCase(
                            workflow_repository=PostgresWorkflowRepository(session),
                            execution_repository=PostgresExecutionRepository(session),
                            state_store=self._state_store,
                            message_broker=self._broker,
                            metrics=metrics_registry,
                        )
                        await use_case.check_all_timeouts()
                        await session.commit()
                except Exception as e:
                    logger.error("timeout_checker_error", error=str(e), exc_info=True)

                await asyncio.sleep(settings.ORCHESTRATOR_TIMEOUT_CHECK_INTERVAL_SECONDS)

        timeout_task = asyncio.create_task(timeout_checker())

        try:
            while not shutdown_event.is_set():
                try:
                    completions = await self._broker.consume_completions(
                        consumer_group=RedisMessageBroker.COMPLETION_GROUP,
                        consumer_name=self._consumer_name,
                        count=settings.ORCHESTRATOR_BATCH_SIZE,
                        block_ms=settings.ORCHESTRATOR_BLOCK_MS,
                    )
                    if completions:
                        await asyncio.gather(*[self.handle_completion(c) for c in completions])
                except Exception as e:
                    logger.error("orchestrator_main_loop_error", error=str(e), exc_info=True)
                    if not shutdown_event.is_set():
                        await asyncio.sleep(settings.ORCHESTRATOR_TIMEOUT_CHECK_INTERVAL_SECONDS)
        finally:
            shutdown_event.set()
            timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await timeout_task
            logger.info("orchestrator_shutdown_complete")

    async def handle_completion(self, completion: CompletionMessage) -> None:
        """Process a single completion with an isolated DB session. ACKs only after commit."""
        try:
            async with async_session_factory() as session:
                use_case = OrchestrateUseCase(
                    workflow_repository=PostgresWorkflowRepository(session),
                    execution_repository=PostgresExecutionRepository(session),
                    state_store=self._state_store,
                    message_broker=self._broker,
                    metrics=metrics_registry,
                )
                await use_case.handle_completion(completion)
                await session.commit()

            if completion.stream_id:
                await self._broker.acknowledge_completion(completion.stream_id)
        except Exception as e:
            # Don't ACK — message stays in PEL for reaper recovery
            logger.error(f"Error handling completion {completion.id}: {e}", exc_info=True)


async def main():
    runner = OrchestratorRunner()
    await runner.run()


if __name__ == "__main__":
    from src.shared.logger import configure_logging

    configure_logging()
    asyncio.run(main())
