from pydantic import BaseModel, Field
from typing import Optional


class LearnRequest(BaseModel):
    run_id: str = Field(..., min_length=1, description="Run identifier")
    tab_id: str = Field(..., min_length=1, description="Frontend tab id")


class LearnResponse(BaseModel):
    ok: bool = Field(..., description="Whether patch was created")
    patch: dict = Field(default_factory=dict, description="Learning patch")
