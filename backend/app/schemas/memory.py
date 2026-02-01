from pydantic import BaseModel, Field
from typing import Optional


class MemoryItem(BaseModel):
    """Memory item from Weaviate"""
    
    id: str = Field(..., description="Memory UUID")
    kind: str = Field(..., description="Memory type")
    key: str = Field(..., description="Memory key")
    text: str = Field(..., description="Memory text")
    tags: list[str] = Field(default_factory=list, description="Memory tags")
    confidence: float = Field(..., description="Confidence score")
    status: str = Field(..., description="Memory status")
    created_at: str = Field(..., description="Creation timestamp")


class MemoryListResponse(BaseModel):
    """Response for GET /v1/memory"""
    
    memories: list[MemoryItem] = Field(..., description="List of memories")
    total: int = Field(..., description="Total count")


class DeleteMemoryRequest(BaseModel):
    """Request for POST /v1/memory/delete"""
    
    user_id: str = Field(..., description="User identifier")
    memory_id: str = Field(..., description="Memory UUID to delete")


class DeleteMemoryResponse(BaseModel):
    """Response for POST /v1/memory/delete"""
    
    success: bool = Field(..., description="Whether deletion succeeded")
    message: str = Field(..., description="Status message")
