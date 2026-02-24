from datetime import datetime, timezone

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from src.shared.config import settings
from src.shared.database import engine
from src.shared.logger import get_logger
from src.shared.redis_client import redis_client

logger = get_logger(__name__)
router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check(response: Response):
    dependencies = {
        "redis": "unknown",
        "postgres": "unknown"
    }
    healthy = True
    
    try:
        await redis_client.ping()
        dependencies["redis"] = "healthy"
    except Exception as e:
        logger.error("health_check_failed", dependency="redis", error=str(e))
        dependencies["redis"] = "unhealthy"
        healthy = False
        
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            dependencies["postgres"] = "healthy"
    except Exception as e:
        logger.error("health_check_failed", dependency="postgres", error=str(e))
        dependencies["postgres"] = "unhealthy"
        healthy = False
        
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
        "dependencies": dependencies
    }
