from pydantic import BaseModel, Field
from typing import Literal


class CanonicalEvent(BaseModel):
    """
    Single source of truth for all events after normalization.
    Every inbound event is converted to this canonical shape before storage.
    """
    
    event_id: str = Field(..., description="Unique identifier for this event (uuid4)")
    trace_id: str = Field(..., description="Groups request/response chains (uuid4)")
    user_id: str = Field(..., description="User identifier (required)")
    session_id: str = Field(..., description="Session identifier (default if missing)")
    provider: str = Field(..., description="Provider name (chatgpt, claude, gemini, browser)")
    event_type: Literal["USER_MESSAGE", "AI_RESPONSE", "NAVIGATE", "PAGE_EXTRACT", "USER_FEEDBACK"] = Field(
        ..., 
        description="Type of event"
    )
    ts_ms: int = Field(..., description="Timestamp in milliseconds (server time if missing)")
    attempt_thread_id: str = Field(..., description="Groups all attempts for the same canonical request")
    payload: dict = Field(..., description="Event payload (must include 'text' for message/response types)")
    
    def validate_payload(self) -> None:
        """Validate payload based on event_type"""
        if self.event_type in ["USER_MESSAGE", "AI_RESPONSE"]:
            if "text" not in self.payload or not self.payload["text"]:
                raise ValueError(f"payload.text is required for event_type={self.event_type}")
