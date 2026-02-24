import logging
import sys
from typing import Any

import structlog


def configure_logging():
    """Configure structlog with JSON output."""
    
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
    return structlog.get_logger(name)

def bind_context(context: dict[str, Any]):
    structlog.contextvars.bind_contextvars(**context)

def unbind_context(*keys: str):
    structlog.contextvars.unbind_contextvars(*keys)

def clear_context():
    structlog.contextvars.clear_contextvars()
