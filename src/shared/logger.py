import structlog
import logging
import sys
from typing import Any, Dict

def configure_logging():
    """
    Configures structural logging for the application.
    Switches to JSON output for production-grade observability.
    """
    
    # Standard Python logging configuration
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str = None):
    """
    Returns a structlog logger.
    """
    return structlog.get_logger(name)

def bind_context(context: Dict[str, Any]):
    """
    Binds additional context to all subsequent log calls in the current context.
    Example: bind_context({"execution_id": "123"})
    """
    structlog.contextvars.bind_contextvars(**context)

def unbind_context(*keys: str):
    """
    Unbinds specific keys from the context.
    """
    structlog.contextvars.unbind_contextvars(*keys)

def clear_context():
    """
    Clears all bound context variables.
    """
    structlog.contextvars.clear_contextvars()
