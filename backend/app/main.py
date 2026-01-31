from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.routes import health
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    print("WeaveIt API starting up...")
    yield
    # Shutdown
    print("Shutting down...")
    redis_client.close()
    weaviate_client.close()


app = FastAPI(
    title="WeaveIt API",
    description="Context-aware memory system with Redis and Weaviate",
    version="0.1.0",
    lifespan=lifespan
)

# Include routers
app.include_router(health.router, tags=["Health"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
