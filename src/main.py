import asyncio
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.adapters.primary.api.dlq_routes import router as dlq_router
from src.adapters.primary.api.error_handlers import (
    general_exception_handler,
    workflow_exception_handler,
)
from src.adapters.primary.api.middleware.rate_limit_middleware import RateLimitMiddleware
from src.adapters.primary.api.routes.health import router as health_router
from src.adapters.primary.api.routes.metrics import router as metrics_router
from src.adapters.primary.api.routes.workflow import router
from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.domain.workflow.exceptions import WorkflowException
from src.shared.config import settings
from src.shared.database import engine
from src.shared.logger import configure_logging, get_logger
from src.shared.redis_client import redis_client

# Configure logging early
configure_logging()
logger = get_logger(__name__)

shutdown_event = asyncio.Event()

def signal_handler():
    logger.info("shutdown_signal_received")
    shutdown_event.set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    except (NotImplementedError, ValueError, RuntimeError):
        pass

    broker = RedisMessageBroker(redis_client)
    await broker.create_consumer_groups()

    logger.info("application_started", version=settings.APP_VERSION)
    yield

    logger.info("application_shutting_down")
    await redis_client.close()
    await engine.dispose()
    logger.info("application_shutdown_complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="Production-grade distributed DAG orchestration engine.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Production Middleware
app.add_middleware(RateLimitMiddleware)

# Exceptions
app.add_exception_handler(WorkflowException, workflow_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Routes
app.include_router(router)
app.include_router(dlq_router)
app.include_router(health_router)
app.include_router(metrics_router)
