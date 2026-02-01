from pydantic import BaseModel, Field, field_validator
from typing import Literal


class Event(BaseModel):
    """Single event schema with strict validation"""
    
    user_id: str = Field(..., min_length=1, description="User identifier")
    session_id: str = Field(..., min_length=1, description="Session identifier")
    provider: Literal["browser", "chatgpt", "claude", "gemini", "generic_web"] = Field(
        ..., description="Event source provider"
    )
    event_type: Literal["NAVIGATE", "PAGE_EXTRACT", "CHAT_TURN", "PAGE_TYPE"] = Field(
        ..., description="Type of event"
    )
    url: str | None = Field(None, description="URL if applicable")
    title: str | None = Field(None, description="Page or chat title")
    ts: int = Field(..., gt=0, description="Unix timestamp in milliseconds")
    payload: dict = Field(default_factory=dict, description="Additional event data")
    
    @field_validator("ts")
    @classmethod
    def validate_timestamp(cls, v: int) -> int:
        """Ensure timestamp is reasonable (after 2020, before 2100)"""
        if v < 1577836800000 or v > 4102444800000:
            raise ValueError("Timestamp must be between 2020 and 2100")
        return v


class EventBatch(BaseModel):
    """Batch of events for ingestion"""
    
    events: list[Event] = Field(..., min_length=1, max_length=100, description="List of events")
    
    @field_validator("events")
    @classmethod
    def validate_events_not_empty(cls, v: list[Event]) -> list[Event]:
        """Ensure events list is not empty"""
        if not v:
            raise ValueError("Events list cannot be empty")
        return v
