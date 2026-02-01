from contextlib import asynccontextmanager
import signal
import asyncio
from fastapi import FastAPI

from src.adapters.primary.api.routes.workflow import router
from src.adapters.primary.api.dlq_routes import router as dlq_router
from src.adapters.primary.api.routes.health import router as health_router
from src.adapters.primary.api.routes.metrics import router as metrics_router
from src.adapters.primary.api.middleware.rate_limit_middleware import RateLimitMiddleware
from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.shared.database import engine
from src.shared.redis_client import redis_client
from src.shared.logger import configure_logging, get_logger

# Configure logging early
configure_logging()
logger = get_logger(__name__)

shutdown_event = asyncio.Event()

def signal_handler():
    logger.info("shutdown_signal_received")
    shutdown_event.set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register signal handlers for graceful shutdown if supported
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    except (NotImplementedError, ValueError, RuntimeError):
        # - NotImplementedError: Signals not supported on some platforms (e.g. Windows)
        # - ValueError/RuntimeError: Can happen in some test environments or non-main threads
        pass

    broker = RedisMessageBroker(redis_client)
    await broker.create_consumer_groups()

    logger.info("application_started", version="1.0.0")
    yield
    
    logger.info("application_shutting_down")
    await redis_client.close()
    await engine.dispose()
    logger.info("application_shutdown_complete")


app = FastAPI(
    title="Applied AI Challenge: Workflow Engine",
    description="Production-grade distributed DAG orchestration engine.",
    version="1.0.0",
    lifespan=lifespan,
)

# Production Middleware
app.add_middleware(RateLimitMiddleware)

# Exceptions
from src.domain.workflow.exceptions import WorkflowException
from src.adapters.primary.api.error_handlers import workflow_exception_handler, general_exception_handler

app.add_exception_handler(WorkflowException, workflow_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Routes
app.include_router(router)
app.include_router(dlq_router)
app.include_router(health_router)
app.include_router(metrics_router)
