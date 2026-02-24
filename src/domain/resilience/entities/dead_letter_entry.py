from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class DeadLetterEntry:
    task_id: str
    execution_id: str
    node_id: str
    handler: str
    config: dict[str, Any]
    error_message: str
    retry_count: int
    original_timestamp: datetime
    id: str = field(default_factory=lambda: str(uuid4()))
    failed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "node_id": self.node_id,
            "handler": self.handler,
            "config": self.config,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "original_timestamp": self.original_timestamp.isoformat(),
            "failed_at": self.failed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeadLetterEntry":
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            execution_id=data["execution_id"],
            node_id=data["node_id"],
            handler=data["handler"],
            config=data["config"],
            error_message=data["error_message"],
            retry_count=data["retry_count"],
            original_timestamp=datetime.fromisoformat(data["original_timestamp"]),
            failed_at=datetime.fromisoformat(data["failed_at"]),
        )
