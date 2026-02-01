from datetime import datetime, timezone
from fastapi import APIRouter, status
from src.shared.redis_client import redis_client
from src.shared.database import engine
from sqlalchemy import select, text
from src.shared.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    """
    Health check endpoint that verifies connectivity to downstream dependencies.
    """
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
        
    status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return {
        "status": "healthy" if healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "dependencies": dependencies
    }
