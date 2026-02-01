from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class RunRequest(BaseModel):
    goal: str = Field(..., description="High-level task goal")
    query: str = Field(..., description="Search query or target topic")
    limit: int = Field(5, description="How many items to collect")
    tab_id: Optional[str] = Field(None, description="Active tab id")
    url: Optional[str] = Field(None, description="Active tab URL")


class RunResponse(BaseModel):
    run_id: str
    status: str
    steps: List[str]
    notes: List[str]


class LearnedStateResponse(BaseModel):
    preferences: Dict[str, str]
    tab_id: Optional[str] = None
