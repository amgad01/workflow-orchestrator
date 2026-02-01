from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    reset_at: Optional[datetime] = None

    @property
    def retry_after_seconds(self) -> Optional[int]:
        if self.allowed or not self.reset_at:
            return None
        delta = (self.reset_at - datetime.now(timezone.utc)).total_seconds()
        return max(1, int(delta))
