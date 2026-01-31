from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    app_env: str = "dev"
    redis_url: str = "redis://localhost:6379/0"
    weaviate_url: str = "http://localhost:8080"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
