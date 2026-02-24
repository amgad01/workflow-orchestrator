import asyncio
import random

from src.adapters.secondary.workers.base_worker import BaseWorker
from src.ports.secondary.message_broker import TaskMessage
from src.shared.config import settings


class LLMServiceWorker(BaseWorker):
    @property
    def handler_name(self) -> str:
        return "call_llm"

    async def process(self, task: TaskMessage) -> dict:
        # Simulate LLM API call with configurable delay
        if settings.WORKER_ENABLE_DELAYS:
            delay = random.uniform(
                settings.WORKER_LLM_MIN_MS / 1000, settings.WORKER_LLM_MAX_MS / 1000
            )
            await asyncio.sleep(delay)

        # Failure simulation for testing
        if task.config.get("simulate_failure", False):
            raise Exception("Simulated LLM service failure")

        prompt = task.config.get("prompt", "No prompt provided")
        model = task.config.get("model", settings.WORKER_DEFAULT_LLM_MODEL)
        temperature = task.config.get("temperature", settings.WORKER_DEFAULT_LLM_TEMPERATURE)
        max_tokens = task.config.get("max_tokens", settings.WORKER_DEFAULT_LLM_MAX_TOKENS)

        responses = [
            "Based on the analysis, the recommended approach is to proceed with option A.",
            "The data suggests a positive correlation between the variables.",
            "I've summarized the key points from the document as requested.",
            "The workflow has been processed successfully with the provided parameters.",
        ]

        return {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt": prompt,
            "response": random.choice(responses),
            "tokens_used": random.randint(100, max_tokens),
        }
