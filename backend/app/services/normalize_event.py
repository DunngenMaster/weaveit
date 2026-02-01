from uuid import uuid4
from datetime import datetime
from typing import Dict, Any
from app.schemas.canonical import CanonicalEvent


def normalize(raw: Dict[str, Any]) -> CanonicalEvent:
    """
    Convert any raw event format to CanonicalEvent.
    
    Args:
        raw: Raw event dict with various possible formats
        
    Returns:
        CanonicalEvent with all required fields populated
        
    Raises:
        ValueError: If required fields are missing
    """
    
    # Required fields - must be present in raw input
    if "user_id" not in raw:
        raise ValueError("user_id is required")
    if "provider" not in raw:
        raise ValueError("provider is required")
    if "event_type" not in raw:
        raise ValueError("event_type is required")
    
    # Generate unique event ID
    event_id = str(uuid4())
    
    # Reuse trace_id if present, otherwise generate new one
    trace_id = raw.get("trace_id", str(uuid4()))
    
    # Use server timestamp if not provided
    ts_ms = raw.get("ts_ms") or raw.get("ts") or int(datetime.now().timestamp() * 1000)
    
    # Default session_id if not provided
    session_id = raw.get("session_id", "default")
    
    # Initialize payload from raw or empty dict
    payload = raw.get("payload", {}).copy() if "payload" in raw else {}
    
    # If raw has 'text' at top level, move it to payload
    if "text" in raw and "text" not in payload:
        payload["text"] = raw["text"]
    
    # Attempt thread ID will be filled by attempt tracking system
    # For now, set to empty string (will be updated before storage)
    attempt_thread_id = raw.get("attempt_thread_id", "")
    
    canonical = CanonicalEvent(
        event_id=event_id,
        trace_id=trace_id,
        user_id=raw["user_id"],
        session_id=session_id,
        provider=raw["provider"],
        event_type=raw["event_type"],
        ts_ms=ts_ms,
        attempt_thread_id=attempt_thread_id,
        payload=payload
    )
    
    # Validate payload based on event type
    canonical.validate_payload()
    
    return canonical
