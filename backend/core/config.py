import os

# Remove any injected PostgreSQL DATABASE_URL before pydantic reads env
os.environ.pop("DATABASE_URL", None)

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "YouTube Shorts Factory"
    APP_VERSION: str = "2.0.0"

    # Auth
    SECRET_KEY: str = os.getenv("SESSION_SECRET", "change-me-in-production-please")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Database
    DATABASE_URL: str = "sqlite:///./shortsdb.sqlite"

    # Encryption (Fernet key untuk credentials)
    FERNET_KEY: str = os.getenv("FERNET_KEY", "")

    # YouTube OAuth
    YOUTUBE_CLIENT_ID: str = os.getenv("YOUTUBE_CLIENT_ID", "")
    YOUTUBE_CLIENT_SECRET: str = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    YOUTUBE_REDIRECT_URI: str = os.getenv(
        "YOUTUBE_REDIRECT_URI", "http://localhost:5000/api/channels/oauth-callback"
    )

    # TikTok
    TIKTOK_CLIENT_KEY: str = os.getenv("TIKTOK_CLIENT_KEY", "")
    TIKTOK_CLIENT_SECRET: str = os.getenv("TIKTOK_CLIENT_SECRET", "")
    TIKTOK_REDIRECT_URI: str = os.getenv(
        "TIKTOK_REDIRECT_URI", "http://localhost:5000/api/channels/tiktok-callback"
    )

    # Meta (Instagram & Facebook)
    META_APP_ID: str = os.getenv("META_APP_ID", "")
    META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
    META_REDIRECT_URI: str = os.getenv(
        "META_REDIRECT_URI", "http://localhost:5000/api/channels/meta-callback"
    )

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Twilio (WhatsApp)
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
