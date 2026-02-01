import asyncio

from src.adapters.secondary.workers.base_worker import BaseWorker
from src.ports.secondary.message_broker import TaskMessage
from src.shared.config import settings


class InputWorker(BaseWorker):
    @property
    def handler_name(self) -> str:
        return "input"

    async def process(self, task: TaskMessage) -> dict:
        if settings.WORKER_ENABLE_DELAYS:
            await asyncio.sleep(settings.WORKER_IO_DELAY_MS / 1000)
        return {"initialized": True, **task.config}


class OutputWorker(BaseWorker):
    @property
    def handler_name(self) -> str:
        return "output"

    async def process(self, task: TaskMessage) -> dict:
        if settings.WORKER_ENABLE_DELAYS:
            await asyncio.sleep(settings.WORKER_IO_DELAY_MS / 1000)
        return {"aggregated": True, "config": task.config}
