from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # === Application ===
    APP_NAME: str = "Workflow Orchestrator"
    APP_VERSION: str = "1.0.0"

    # === Database ===
    database_url: str = "postgresql+asyncpg://workflow:workflow@localhost:5432/workflow"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # AWS RDS component fields (override database_url when set)
    DB_HOST: str | None = None
    DB_PORT: int = 5432
    DB_USERNAME: str | None = None
    DB_PASSWORD: str | None = None
    DB_NAME: str = "workflow"

    # === Redis ===
    redis_url: str = "redis://localhost:6379/0"

    # AWS ElastiCache component fields (override redis_url when set)
    REDIS_HOST: str | None = None
    REDIS_PORT: int = 6379

    # === Worker: batch & polling ===
    WORKER_BATCH_SIZE: int = 50
    WORKER_BLOCK_MS: int = 2000
    WORKER_ENABLE_DELAYS: bool = True

    # Worker: simulated delay ranges (milliseconds)
    WORKER_IO_DELAY_MS: int = 100
    WORKER_INPUT_MIN_MS: int = 50
    WORKER_INPUT_MAX_MS: int = 150
    WORKER_EXTERNAL_MIN_MS: int = 1000
    WORKER_EXTERNAL_MAX_MS: int = 2000
    WORKER_LLM_MIN_MS: int = 1500
    WORKER_LLM_MAX_MS: int = 2500
    WORKER_DECISION_MIN_MS: int = 10
    WORKER_DECISION_MAX_MS: int = 50

    # Worker: handler fallback defaults
    WORKER_DEFAULT_EXTERNAL_URL: str = "http://example.com/api"
    WORKER_DEFAULT_LLM_MODEL: str = "gpt-4"
    WORKER_DEFAULT_LLM_TEMPERATURE: float = 0.7
    WORKER_DEFAULT_LLM_MAX_TOKENS: int = 1000

    # Worker: retry / backoff
    WORKER_MAX_RETRIES: int = 3
    WORKER_BACKOFF_BASE_SECONDS: float = 1.0
    WORKER_BACKOFF_MAX_SECONDS: float = 30.0
    WORKER_BACKOFF_JITTER_MAX: float = 0.5
    WORKER_IDEMPOTENCY_TTL_SECONDS: int = 86400

    # === Orchestrator ===
    ORCHESTRATOR_BATCH_SIZE: int = 100
    ORCHESTRATOR_BLOCK_MS: int = 2000
    ORCHESTRATOR_TIMEOUT_CHECK_INTERVAL_SECONDS: float = 1.0

    # === Reaper ===
    REAPER_CHECK_INTERVAL_SECONDS: int = 60
    REAPER_MIN_IDLE_SECONDS: int = 300
    REAPER_BATCH_SIZE: int = 10

    # === Distributed Lock ===
    LOCK_TTL_SECONDS: int = 30

    # === DAG Cache ===
    DAG_CACHE_MAX_SIZE: int = 256
    DAG_CACHE_TTL_SECONDS: int = 300  # 5 min — aligned with reaper idle threshold

    # === Workflow ===
    EXECUTION_METADATA_TTL_SECONDS: int = 86400

    # === Redis Streams ===
    STREAM_TASK_KEY: str = "workflow:tasks"
    STREAM_COMPLETION_KEY: str = "workflow:completions"
    STREAM_DLQ_KEY: str = "workflow:dlq"
    STREAM_DLQ_INDEX_KEY: str = "workflow:dlq:index"
    STREAM_TASK_GROUP: str = "task_workers"
    STREAM_COMPLETION_GROUP: str = "orchestrators"
    STREAM_MAX_LEN: int = 10000

    # === Rate Limiting ===
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 300
    RATE_LIMIT_BURST_SIZE: int = 10
    RATE_LIMIT_ENABLED: bool = True

    # === Circuit Breaker ===
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS: int = 60
    CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS: int = 2
    CIRCUIT_BREAKER_ENABLED: bool = True

    # === Worker: error loop pause ===
    WORKER_ERROR_PAUSE_SECONDS: float = 1.0

    # === Dead Letter Queue ===
    DLQ_MAX_RETRIES: int = 3
    DLQ_ENABLED: bool = True

    # === Concurrency ===
    MAX_CONCURRENT_DB_OPERATIONS: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def construct_urls_from_components(self) -> "Settings":
        """Construct database_url/redis_url from individual AWS components."""
        if self.DB_HOST and self.DB_USERNAME and self.DB_PASSWORD:
            self.database_url = (
                f"postgresql+asyncpg://{self.DB_USERNAME}:{self.DB_PASSWORD}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        if self.REDIS_HOST:
            self.redis_url = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return self

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
