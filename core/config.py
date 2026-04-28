from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    PROJECT_NAME: str = "Trip Road API"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str
    CHROMADB_HOST: str
    CHROMADB_PORT: int
    CELERY_BROKER_URL: str
    OPENAI_API_KEY: str
    GOOGLE_OAUTH_CLIENT_ID: str
    WEATHER_API_KEY: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1일
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 14  # 14일

    class Config:
        env_file = str(BASE_DIR / ".env")


settings = Settings()
