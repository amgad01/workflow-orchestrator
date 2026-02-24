from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    reset_at: datetime | None = None

    @property
    def retry_after_seconds(self) -> int | None:
        if self.allowed or not self.reset_at:
            return None
        delta = (self.reset_at - datetime.now(timezone.utc)).total_seconds()
        return max(1, int(delta))
