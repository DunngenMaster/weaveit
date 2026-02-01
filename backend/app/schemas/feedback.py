from pydantic import BaseModel, Field
from typing import Optional


class FeedbackRequest(BaseModel):
    run_id: str = Field(..., min_length=1, description="Run identifier")
    tab_id: str = Field(..., min_length=1, description="Frontend tab id")
    tags: list[str] = Field(default_factory=list, description="Feedback tags")
    notes: Optional[str] = Field(None, description="Optional notes")


class FeedbackResponse(BaseModel):
    ok: bool = Field(..., description="Whether feedback was stored")
