from pydantic_settings import BaseSettings
from functools import lru_cache
import os


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
    
    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        case_sensitive = False
        extra = "ignore"

def get_settings() -> Settings:
    return Settings()
