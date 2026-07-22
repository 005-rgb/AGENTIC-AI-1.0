import os

# Remove any injected PostgreSQL DATABASE_URL before pydantic reads env
os.environ.pop("DATABASE_URL", None)

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "YouTube Shorts Factory"
    APP_VERSION: str = "1.0.0"
    SECRET_KEY: str = os.getenv("SESSION_SECRET", "change-me-in-production-please")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    DATABASE_URL: str = "sqlite:///./shortsdb.sqlite"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
