from pydantic import BaseModel, Field


class BrowserSessionStartRequest(BaseModel):
    """Request for POST /v1/browser/session/start"""
    
    user_id: str = Field(..., description="User identifier")


class BrowserSessionStartResponse(BaseModel):
    """Response for POST /v1/browser/session/start"""
    
    session_id: str = Field(..., description="Browserbase session ID")
    user_id: str = Field(..., description="User identifier")
    connect_url: str = Field(..., description="WebSocket URL to connect to the session")
    status: str = Field(..., description="Session status")


class ExtractJobRequest(BaseModel):
    """Request for POST /v1/browser/extract/job"""
    
    user_id: str = Field(..., description="User identifier")
    url: str = Field(..., description="Job posting URL")


class ExtractJobResponse(BaseModel):
    """Response for POST /v1/browser/extract/job"""
    
    ok: bool = Field(..., description="Success status")
    extracted: dict = Field(..., description="Extracted job data")
