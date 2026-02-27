import traceback as tb_module
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any


class ErrorCategory(str, Enum):
    """Classification of DLQ errors for automated retry decisions."""

    TRANSIENT = "transient"  # Network timeouts, temporary unavailability
    VALIDATION = "validation"  # Bad input, schema mismatch
    RESOURCE = "resource"  # Rate limits, quota exceeded
    INFRASTRUCTURE = "infrastructure"  # DB connection, Redis failure
    HANDLER = "handler"  # Worker handler bug / unhandled exception
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ErrorDetail:
    """Structured error payload for DLQ entries.

    Replaces plain error strings with a schema that supports
    automated retry classification and operability tooling.
    """

    message: str
    error_code: str = "UNCLASSIFIED"
    category: ErrorCategory = ErrorCategory.UNKNOWN
    traceback_hash: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        *,
        category: ErrorCategory | None = None,
        error_code: str | None = None,
    ) -> "ErrorDetail":
        """Build an ErrorDetail from a caught exception."""
        tb_str = "".join(tb_module.format_exception(type(exc), exc, exc.__traceback__))
        tb_hash = sha256(tb_str.encode()).hexdigest()[:12]

        resolved_category = category or _classify_exception(exc)
        resolved_code = error_code or type(exc).__name__

        return cls(
            message=str(exc),
            error_code=resolved_code,
            category=resolved_category,
            traceback_hash=tb_hash,
        )

    @classmethod
    def from_message(cls, message: str) -> "ErrorDetail":
        """Create from a plain string (backward-compatible)."""
        return cls(message=message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "error_code": self.error_code,
            "category": self.category.value,
            "traceback_hash": self.traceback_hash,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorDetail":
        # Backward compatibility: handle plain string error_message
        if isinstance(data, str):
            return cls(message=data)
        return cls(
            message=data.get("message", ""),
            error_code=data.get("error_code", "UNCLASSIFIED"),
            category=ErrorCategory(data.get("category", "unknown")),
            traceback_hash=data.get("traceback_hash", ""),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data
            else datetime.now(timezone.utc),
        )


def _classify_exception(exc: Exception) -> ErrorCategory:
    """Auto-classify common exception types into error categories."""
    exc_name = type(exc).__name__.lower()
    exc_msg = str(exc).lower()

    # Transient errors
    transient_patterns = ("timeout", "connection", "temporary", "unavailable", "retry")
    if any(p in exc_name or p in exc_msg for p in transient_patterns):
        return ErrorCategory.TRANSIENT

    # Validation errors
    validation_patterns = ("validation", "invalid", "schema", "parsing", "value")
    if any(p in exc_name or p in exc_msg for p in validation_patterns):
        return ErrorCategory.VALIDATION

    # Resource errors
    resource_patterns = ("ratelimit", "rate_limit", "quota", "throttl")
    if any(p in exc_name or p in exc_msg for p in resource_patterns):
        return ErrorCategory.RESOURCE

    # Infrastructure errors (checked by type name only, not message)
    infra_patterns = ("redis", "postgres", "database", "sql")
    if any(p in exc_name for p in infra_patterns):
        return ErrorCategory.INFRASTRUCTURE

    return ErrorCategory.UNKNOWN
