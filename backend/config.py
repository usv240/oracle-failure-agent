from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "oracle_db"
    GOOGLE_PROJECT_ID: str
    GOOGLE_LOCATION: str = "us-central1"
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"  # Vertex AI fallback model
    APP_PORT: int = 8080
    OUTPUT_DIR: str = "outputs"
    VOYAGE_API_KEY: str = ""     # MongoDB Voyage AI — voyage-4-large embeddings
    SLACK_WEBHOOK_URL: str = ""  # Optional — Slack incoming webhook for monitoring alerts
    APP_URL: str = "http://localhost:8080"  # Public URL of the deployed app (used in Slack alerts)

    class Config:
        env_file = ".env"


settings = Settings()
OUTPUT_PATH = Path(settings.OUTPUT_DIR)
OUTPUT_PATH.mkdir(exist_ok=True)
