from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Union

# Dev origins always allowed — these never break local development
_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost",
    "http://127.0.0.1",
]

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres123@localhost:5432/quizzie_db"

    # Security
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS — comma-separated string from env, e.g. "https://myapp.com,https://api.myapp.com"
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
        """Dev origins + any extra origins from CORS_ORIGINS env var, deduplicated."""
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

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
