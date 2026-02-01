from fastapi import Request, status
from fastapi.responses import JSONResponse
from src.domain.workflow.exceptions import WorkflowException
from src.shared.logger import get_logger

logger = get_logger(__name__)

async def workflow_exception_handler(request: Request, exc: WorkflowException):
    """
    Global exception handler for WorkflowException and its subclasses.
    Converts domain exceptions to structured JSON responses.
    """
    logger.error(
        "workflow_error",
        error_code=exc.error_code,
        message=exc.message,
        context=exc.context,
        path=request.url.path
    )
    
    # Map error codes to HTTP status codes
    status_code = status.HTTP_400_BAD_REQUEST
    if exc.error_code == "EXECUTION_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": exc.message,
                "error_code": exc.error_code,
                "context": exc.context
            }
        }
    )

async def general_exception_handler(request: Request, exc: Exception):
    """
    Fallback handler for all unhandled exceptions.
    """
    logger.exception("unhandled_exception", path=request.url.path)
    
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": "Internal processing error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "context": {"type": str(type(exc).__name__)}
            }
        }
    )
