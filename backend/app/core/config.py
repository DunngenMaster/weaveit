from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os
from pathlib import Path

# Get backend directory (where .env is located)
BACKEND_DIR = Path(__file__).parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    
    app_env: str = "dev"
    redis_url: str = "redis://localhost:6379/0"
    redis_api_key: str = ""
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    browserbase_api_key: str = ""
    browserbase_project_id: str = ""
    
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        case_sensitive=False,
        extra="ignore"
    )

def get_settings() -> Settings:
    return Settings()
