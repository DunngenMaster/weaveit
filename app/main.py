from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings

app = FastAPI(title="Ghost Mode Agent", version="0.1.0")

app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok", "env": settings.app_env}
