from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "local")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    weave_project: str = os.getenv("WEAVE_PROJECT", "")
    wandb_entity: str = os.getenv("WANDB_ENTITY", "")
    wandb_project: str = os.getenv("WANDB_PROJECT", "")
    browserbase_api_key: str = os.getenv("BROWSERBASE_API_KEY", "")
    gcs_bucket: str = os.getenv("GCS_BUCKET", "")


settings = Settings()
