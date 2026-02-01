from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.routes import health, events, context, memory, browser, demo
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client
from app.services.db_client import db_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("WeaveIt API starting up...")
    db_client.connect()
    weaviate_client.create_schema()
    yield
    print("Shutting down...")
    redis_client.close()
    weaviate_client.close()
    db_client.close()


app = FastAPI(
    title="WeaveIt API",
    description="Context-aware memory system with Redis and Weaviate",
    version="0.1.0",
    lifespan=lifespan
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(events.router, tags=["Events"])
app.include_router(context.router, tags=["Context"])
app.include_router(memory.router, tags=["Memory"])
app.include_router(browser.router, tags=["Browser"])
app.include_router(demo.router, tags=["Demo"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
