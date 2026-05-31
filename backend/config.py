from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "oracle_db"
    GOOGLE_PROJECT_ID: str
    GOOGLE_LOCATION: str = "us-central1"
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"          # Vertex AI scoring model
    ADK_MODEL: str = "gemini-3-flash-preview"        # Gemini 3 Flash for ADK agents
    VOYAGE_MODEL: str = "voyage-4-large"             # Primary embedding model
    EMBED_FALLBACK_MODEL: str = "text-embedding-004" # Fallback embedding (Google)
    APP_PORT: int = 8080
    OUTPUT_DIR: str = "outputs"
    VOYAGE_API_KEY: str = ""     # MongoDB Voyage AI embeddings
    SLACK_WEBHOOK_URL: str = ""  # Optional — Slack incoming webhook for monitoring alerts
    APP_URL: str = "http://localhost:8080"  # Public URL of the deployed app (used in Slack alerts)

    class Config:
        env_file = ".env"


settings = Settings()
OUTPUT_PATH = Path(settings.OUTPUT_DIR)
OUTPUT_PATH.mkdir(exist_ok=True)
