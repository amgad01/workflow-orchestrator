from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter, Response

router = APIRouter(tags=["Metrics"])

@router.get("/metrics")
async def metrics():
    """
    Exposed Prometheus metrics endpoint.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
