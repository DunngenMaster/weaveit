from fastapi import APIRouter
from app.models import RunRequest, RunResponse, LearnedStateResponse
from app.agent.loop import run_agent
from app.memory.redis_store import MemoryStore

router = APIRouter()

memory = MemoryStore()


@router.post("/runs", response_model=RunResponse)
def create_run(payload: RunRequest):
    run = run_agent(payload, memory)
    return run


@router.get("/learned", response_model=LearnedStateResponse)
def learned_state():
    return LearnedStateResponse(preferences=memory.get_preferences())
