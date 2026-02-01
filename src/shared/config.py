from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database configuration
    database_url: str = "postgresql+asyncpg://workflow:workflow@localhost:5432/workflow"
    
    # Redis configuration
    redis_url: str = "redis://localhost:6379/0"
    
    # Worker delay configuration (milliseconds)
    WORKER_ENABLE_DELAYS: bool = True
    WORKER_IO_DELAY_MS: int = 100
    WORKER_EXTERNAL_MIN_MS: int = 1000
    WORKER_EXTERNAL_MAX_MS: int = 2000
    WORKER_LLM_MIN_MS: int = 1500
    WORKER_LLM_MAX_MS: int = 2500
    
    # Concurrency control
    MAX_CONCURRENT_DB_OPERATIONS: int = 50
    
    # Message broker batch configuration
    ORCHESTRATOR_BATCH_SIZE: int = 100
    ORCHESTRATOR_BLOCK_MS: int = 2000
    WORKER_BATCH_SIZE: int = 50
    WORKER_BLOCK_MS: int = 2000

    # Rate Limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 300
    RATE_LIMIT_BURST_SIZE: int = 10
    RATE_LIMIT_ENABLED: bool = True

    # Circuit Breaker
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS: int = 60
    CIRCUIT_BREAKER_ENABLED: bool = True

    # Dead Letter Queue
    DLQ_MAX_RETRIES: int = 3
    DLQ_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("RATE_LIMIT_REQUESTS_PER_MINUTE")
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Rate limit must be positive")
        return v


try:
    settings = Settings()
except Exception as e:
    import sys
    print(f"CRITICAL: Configuration validation failed: {e}")
    sys.exit(1)
