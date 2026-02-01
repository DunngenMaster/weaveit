from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.routes import (
    health,
    events,
    context,
    memory,
    browser,
    demo,
    runs,
    feedback,
    debug,
    eval,
    audit,
    handoff,
    run_events,
)
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

# Dev CORS for local Electron/Vite
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(events.router, tags=["Events"])
app.include_router(context.router, tags=["Context"])
app.include_router(memory.router, tags=["Memory"])
app.include_router(browser.router, tags=["Browser"])
app.include_router(demo.router, tags=["Demo"])
app.include_router(runs.router, tags=["Runs"])
app.include_router(feedback.router, tags=["Feedback"])
app.include_router(debug.router, tags=["Debug"])  # Sprint 15.6
app.include_router(eval.router, tags=["Eval"])  # Sprint 16.5 & 16.6
app.include_router(audit.router, tags=["Audit"])  # Sprint 17.10
app.include_router(handoff.router, tags=["Handoff"])  # Sprint 18: CSA
app.include_router(run_events.router, tags=["Run Events"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
