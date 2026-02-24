import asyncio
import signal
from uuid import uuid4

from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.shared.config import settings
from src.shared.logger import get_logger
from src.shared.redis_client import redis_client

logger = get_logger(__name__)

class ReaperRunner:
    """Recovers zombie tasks from the Redis PEL via XAUTOCLAIM, re-publishes them, and ACKs the originals."""
    def __init__(
        self,
        check_interval_seconds: int | None = None,
        min_idle_seconds: int | None = None,
    ):
        self._broker = RedisMessageBroker(redis_client)
        self._check_interval = check_interval_seconds if check_interval_seconds is not None else settings.REAPER_CHECK_INTERVAL_SECONDS
        self._min_idle_ms = (min_idle_seconds if min_idle_seconds is not None else settings.REAPER_MIN_IDLE_SECONDS) * 1000
        self._consumer_name = f"reaper-{uuid4().hex[:8]}"

    async def run(self):
        logger.info(f"Reaper started (consumer={self._consumer_name}). Watching for tasks idle > {self._min_idle_ms}ms...")
        
        await self._broker.create_consumer_groups()

        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def signal_handler():
            logger.info("Reaper received shutdown signal. Stopping...")
            shutdown_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)

        while not shutdown_event.is_set():
            try:
                # 1. Claim stalled tasks (XAUTOCLAIM)
                tasks = await self._broker.claim_stalled_tasks(
                    consumer_group=RedisMessageBroker.TASK_GROUP,
                    new_consumer=self._consumer_name,
                    min_idle_ms=self._min_idle_ms,
                    count=10
                )

                if tasks:
                    logger.info(f"Reaper reclaimed {len(tasks)} zombie tasks.")
                    for stream_id, task in tasks:
                        if shutdown_event.is_set():
                             logger.info("Reaper shutdown pending, waiting for next cycle...")
                             break
                             
                        # 2. Resurrect
                        await self._broker.publish_task(task)
                        
                        # 3. Bury
                        await self._broker.acknowledge_task(stream_id)
                        logger.info(f"Resurrected task execution_id={task.execution_id} node_id={task.node_id}")

            except Exception as e:
                logger.error(f"Reaper error: {e}")
            
            # Wait with check
            if not shutdown_event.is_set():
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=self._check_interval)
                except asyncio.TimeoutError:
                    pass
        
        logger.info("Reaper shutdown complete.")

if __name__ == "__main__":
    from src.shared.logger import configure_logging
    configure_logging()
    reaper = ReaperRunner()
    asyncio.run(reaper.run())
