from pydantic import BaseModel, Field


class ContextResponse(BaseModel):
    """Response for GET /v1/context endpoint"""
    
    context_block: str = Field(..., description="Formatted context string for injection")
    active_goal: str = Field(default="", description="Current active goal/task")
    next_steps: list[str] = Field(default_factory=list, description="Suggested next actions")
