from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Union

_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost",
    "http://127.0.0.1",
]

_KNOWN_INSECURE_SECRETS = {
    "dev-only-insecure-secret-change-me",
    # The previous hard-coded default — it is in the public git history.
    "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
    # Placeholders shipped in .env.example / .env.production.
    "your-secret-key-change-this-in-production",
    "CHANGE_THIS_TO_A_RANDOM_SECRET_KEY",
}


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres123@localhost:5432/quizzie_db"

    # Direct Postgres URL for migrations. Needed when DATABASE_URL points at
    # PgBouncer in transaction mode: the migration advisory lock is
    # session-level and must not be multiplexed. Empty = use DATABASE_URL.
    MIGRATION_DATABASE_URL: str = ""

    # Connection budget (per process). With the run_db rule a connection is
    # only held inside a threadpool call, so a process never needs more than
    # THREADPOOL_SIZE connections. Fleet-wide:
    #   sum over processes of (DB_POOL_SIZE + DB_MAX_OVERFLOW) <= Postgres
    #   max_connections - reserve   (or put PgBouncer in front).
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    THREADPOOL_SIZE: int = 40               # anyio default; FastAPI's sync-route pool

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 512        # per API process (async pool)
    # Optional separate Redis for the Celery broker (run it with
    # maxmemory-policy noeviction). Empty = share REDIS_URL.
    CELERY_BROKER_URL: str = ""

    # Security
    # Dev-only default. This value is public (it's in git), so anyone could
    # mint valid JWTs with it; assert_production_safe() refuses to boot a
    # production process that still uses it.
    SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120   # 2 hours — safe for long exams

    # CORS
    CORS_ORIGINS: Union[List[str], str] = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def all_cors_origins(self) -> List[str]:
        extra = self.CORS_ORIGINS if isinstance(self.CORS_ORIGINS, list) else []
        combined = _DEV_ORIGINS + [o for o in extra if o not in _DEV_ORIGINS]
        return combined

    # App
    APP_NAME: str = "Quizzie API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    # Frontend URL (used in email links)
    FRONTEND_URL: str = "http://localhost:5173"

    # Email (SMTP)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = "Quizzie"

    # Cache TTLs (seconds)
    CACHE_TTL_EXAM_QUESTIONS: int = 300     # 5 min — questions rarely change during live exam
    CACHE_TTL_EXAM_META: int = 60           # 1 min — exam status
    CACHE_TTL_LEADERBOARD: int = 30         # 30 sec — leaderboard
    CACHE_TTL_USER: int = 60                # 60 sec — auth user lookup

    # Exam timing: submissions/auto-saves are accepted until deadline + grace.
    # The grace absorbs network latency and client/server clock drift at the
    # very end of the exam; it is NOT extra answering time for the student
    # (late submit payloads are ignored — see AttemptService.submit).
    SUBMIT_GRACE_SECONDS: int = 30

    # Evaluation: "auto" = Celery if reachable, else inline on demand;
    # "inline" = never queue (tests, single-process dev).
    EVALUATION_MODE: str = "auto"
    # How long GET /results trusts that a queued evaluation is still coming
    # before it evaluates inline itself (covers a crashed worker).
    EVAL_PENDING_TTL_SECONDS: int = 60

    # Proctoring upload limits (per attempt, sliding window, enforced in Redis)
    PROCTOR_RATE_MAX_EVENTS: int = 8
    PROCTOR_RATE_WINDOW_SEC: float = 5.0

    def assert_production_safe(self) -> None:
        if self.ENVIRONMENT.lower() == "production" and (
            self.SECRET_KEY in _KNOWN_INSECURE_SECRETS or len(self.SECRET_KEY) < 32
        ):
            raise RuntimeError(
                "Refusing to start: SECRET_KEY is a known/default value or too short. "
                "Set a random 32+ char SECRET_KEY in the environment."
            )

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
