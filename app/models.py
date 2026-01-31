from pydantic import BaseModel, Field
from typing import List, Dict


class RunRequest(BaseModel):
    goal: str = Field(..., description="High-level task goal")
    query: str = Field(..., description="Search query or target topic")
    limit: int = Field(5, description="How many items to collect")


class RunResponse(BaseModel):
    run_id: str
    status: str
    steps: List[str]
    notes: List[str]


class LearnedStateResponse(BaseModel):
    preferences: Dict[str, str]
