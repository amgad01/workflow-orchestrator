import asyncio
import signal
from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.shared.redis_client import redis_client
from src.shared.logger import get_logger

logger = get_logger(__name__)

class ReaperRunner:
    """
    Background service that recovers "Zombie Tasks".
    
    Zombies are tasks that were claimed by a worker but never completed (due to crash
    or network failure). The Reaper monitors the Pending Entry List (PEL) for
    messages that have exceeded a max idle time.
    
    Strategy: The 'Resurrect and Bury' pattern.
    1. Claim the stuck task.
    2. Re-publish it as a new event (Resurrect).
    3. Acknowledge the old stuck event (Bury).
    """
    def __init__(self, check_interval_seconds: int = 60, min_idle_seconds: int = 300):
        self._broker = RedisMessageBroker(redis_client)
        self._check_interval = check_interval_seconds
        self._min_idle_ms = min_idle_seconds * 1000
        # The reaper joins the consumer group but acts as a special consumer
        self._consumer_name = "reaper-process-01"

    async def run(self):
        logger.info(f"💀 Reaper started. Watching for tasks idle > {self._min_idle_ms}ms...")
        
        # Ensure group exists (idempotent)
        await self._broker.create_consumer_groups()

        # Graceful shutdown setup
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def signal_handler():
            logger.info("💀 Reaper received shutdown signal. Stopping...")
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
                    logger.info(f"💀 Reaper reclaimed {len(tasks)} zombie tasks.")
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
        
        logger.info("💀 Reaper shutdown complete.")

if __name__ == "__main__":
    from src.shared.logger import configure_logging
    configure_logging()
    reaper = ReaperRunner(check_interval_seconds=10, min_idle_seconds=60) # Fast settings for demo
    asyncio.run(reaper.run())
