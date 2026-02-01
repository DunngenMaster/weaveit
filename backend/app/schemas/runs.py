from pydantic import BaseModel, Field
from typing import Optional


class RunStartRequest(BaseModel):
    """Request to start an agent run."""
    
    goal: str = Field(..., min_length=1, description="User goal")
    query: str = Field(..., min_length=1, description="Search query")
    limit: int = Field(5, ge=1, le=25, description="Max results to consider")
    tab_id: str = Field(..., min_length=1, description="Frontend tab id")
    url: Optional[str] = Field(None, description="Current tab URL")


class RunStartResponse(BaseModel):
    """Response for starting an agent run."""
    
    run_id: str = Field(..., description="Run identifier")
    status: str = Field(..., description="Run status")
    status_reason: str | None = Field(None, description="Reason for pause/stop")


class LearnedResponse(BaseModel):
    """Response for learned preferences per tab."""
    
    preferences: dict = Field(default_factory=dict, description="Learned preferences")


class RunDetailsResponse(BaseModel):
    """Response for run details."""
    
    run_id: str = Field(..., description="Run identifier")
    status: str = Field(..., description="Run status")
    goal: str | None = Field(None, description="Run goal")
    query: str | None = Field(None, description="Run query")
    error: str | None = Field(None, description="Error message if any")
    plan: dict = Field(default_factory=dict, description="Planner output")
    candidates: list = Field(default_factory=list, description="Candidate links")
    extracted: list = Field(default_factory=list, description="Extracted items")
    trace: list = Field(default_factory=list, description="Trace events")
    connect_url: str | None = Field(None, description="Browserbase connect URL")
    live_view_url: str | None = Field(None, description="Browserbase live view URL")
    summary: dict = Field(default_factory=dict, description="Summary + comparison")
    patch: dict = Field(default_factory=dict, description="Learning patch")
    applied_policy: dict = Field(default_factory=dict, description="Policy used for this run")
    applied_prompt_delta: dict = Field(default_factory=dict, description="Prompt delta applied")
    metrics: dict = Field(default_factory=dict, description="Run metrics")
