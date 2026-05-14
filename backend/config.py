from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "oracle_db"
    GOOGLE_PROJECT_ID: str
    GOOGLE_LOCATION: str = "us-central1"
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-pro"
    APP_PORT: int = 8080
    OUTPUT_DIR: str = "outputs"

    class Config:
        env_file = ".env"


settings = Settings()
OUTPUT_PATH = Path(settings.OUTPUT_DIR)
OUTPUT_PATH.mkdir(exist_ok=True)
