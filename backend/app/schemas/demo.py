from pydantic import BaseModel, Field


class JobToContextRequest(BaseModel):
    """Request for POST /v1/demo/job_to_context"""
    
    user_id: str = Field(..., description="User identifier")
    job_url: str = Field(..., description="Job posting URL")
    provider: str = Field(..., description="AI provider (chatgpt, claude, gemini)")


class JobToContextResponse(BaseModel):
    """Response for POST /v1/demo/job_to_context"""
    
    context_block: str = Field(..., description="Formatted context block")
    job: dict = Field(..., description="Extracted job data")
