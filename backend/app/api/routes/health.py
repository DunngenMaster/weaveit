from fastapi import APIRouter
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Health check endpoint
    
    Returns status of FastAPI, Redis, and Weaviate services
    """
    
    # Check Redis connectivity
    redis_status = "ok" if redis_client.check_health() else "down"
    
    # Check Weaviate connectivity
    weaviate_status = "ok" if weaviate_client.check_health() else "down"
    
    return {
        "status": "ok",
        "services": {
            "fastapi": "ok",
            "redis": redis_status,
            "weaviate": weaviate_status
        }
    }
