import json
import hashlib
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, status
from app.schemas.events import EventBatch
from app.schemas.canonical import CanonicalEvent
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client
from app.services.memory_writer import memory_writer
from app.services.normalize_event import normalize
from app.services.attempt_thread import attempt_thread_manager
from app.utils.fingerprint import compute_fingerprint as compute_fp


router = APIRouter(prefix="/v1/events")


def is_sensitive_url(url: str | None) -> bool:
    """Check if URL contains sensitive domains that should not be ingested"""
    if not url:
        return False
    
    url_lower = url.lower()
    sensitive_patterns = [
        "mail.google.com",
        "bank",
        "myaccount.google.com",
        "paypal",
        "chase",
        "wellsfargo",
        "health"
    ]
    
    return any(pattern in url_lower for pattern in sensitive_patterns)


def write_memory_to_weaviate(user_id: str, candidate: dict):
    try:
        client = weaviate_client.client
        collection = client.collections.get("MemoryItem")
        
        now = datetime.now(timezone.utc)
        ttl_days = candidate.get("ttl_days", 30)
        
        collection.data.insert({
            "user_id": user_id,
            "kind": candidate.get("kind", "PROFILE"),
            "key": candidate.get("key", ""),
            "text": candidate.get("text", ""),
            "tags": candidate.get("tags", []),
            "source": "chat",
            "source_url": "",
            "confidence": candidate.get("confidence", 0.8),
            "status": "active",
            "created_at": now,
            "last_seen_at": now
        })
        return True
    except Exception as e:
        print(f"Error writing to Weaviate: {e}")
        return False


@router.post("", status_code=status.HTTP_200_OK)
async def ingest_events(batch: EventBatch):
    try:
        client = redis_client.get_client()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis connection unavailable"
            )
        
        ingested_count = 0
        canonical_events = []
        
        # First pass: normalize all events to canonical format
        for event in batch.events:
            # Block sensitive URLs
            if is_sensitive_url(event.url):
                return {"ignored": True, "reason": "SENSITIVE_URL"}
            
            # Convert to dict for normalization
            raw_event = event.model_dump()
            
            # Normalize to canonical event
            try:
                canonical = normalize(raw_event)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event: {str(e)}"
                )
            
            # Handle USER_MESSAGE: compute fingerprint and create/get attempt thread
            if canonical.event_type == "USER_MESSAGE":
                # Compute fingerprint
                text = canonical.payload.get("text", "")
                fingerprint = compute_fp(text)
                canonical.payload["fingerprint"] = fingerprint
                
                # Get or create attempt thread
                attempt_thread_id, attempt_count = attempt_thread_manager.get_or_create_thread(
                    user_id=canonical.user_id,
                    fingerprint=fingerprint,
                    domain="unknown"  # Will be enhanced later
                )
                
                # Generate attempt ID for this specific attempt
                attempt_id = str(uuid4())
                canonical.payload["attempt_id"] = attempt_id
                canonical.attempt_thread_id = attempt_thread_id
                
                # Add attempt record
                attempt_thread_manager.add_attempt_record(
                    attempt_thread_id=attempt_thread_id,
                    attempt_id=attempt_id,
                    event_id=canonical.event_id,
                    trace_id=canonical.trace_id,
                    payload=canonical.payload
                )
                
                print(f"[ATTEMPT] USER_MESSAGE fingerprint={fingerprint[:8]}... thread={attempt_thread_id[:8]}... count={attempt_count}")
            
            # For other event types, set attempt_thread_id to empty or link to trace
            elif canonical.attempt_thread_id == "":
                canonical.attempt_thread_id = canonical.trace_id
            
            canonical_events.append(canonical)
        
        # Second pass: store canonical events
        for canonical in canonical_events:
            
            session_id = event.session_id
            user_id = event.user_id
            
            event_key = f"events:{session_id}"
            event_json = event.model_dump_json()
            client.rpush(event_key, event_json)
            client.expire(event_key, 86400)
            
            state_key = f"session:{user_id}:state"
            state_updates = {
                "last_event_ts": str(canonical.ts_ms),
                "last_provider": canonical.provider,
                "last_event_type": canonical.event_type
            }
            if canonical.payload.get("url"):
                state_updates["last_url"] = canonical.payload["url"]
            
            client.hset(state_key, mapping=state_updates)
            client.expire(state_key, 86400)
            # Handle AI_RESPONSE paired with USER_MESSAGE (for legacy CHAT_TURN support)
            if canonical.event_type in ["USER_MESSAGE", "AI_RESPONSE"]:
                # Store text for potential memory extraction
                if canonical.event_type == "AI_RESPONSE":
                    # Look for paired USER_MESSAGE in same trace
                    user_msg_text = None
                    for c in canonical_events:
                        if c.trace_id == canonical.trace_id and c.event_type == "USER_MESSAGE":
                            user_msg_text = c.payload.get("text", "")
                            break
                    
                    if user_msg_text
                if event.payload and "user_message" in event.payload and "assistant_message" in event.payload:
                    print(f"DEBUG: Starting memory extraction for user {user_id}")
                    user_msg = event.payload["user_message"]
                    asst_msg = event.payload["assistant_message"]
                    
                    recent_summaries = client.lrange(summaries_key, -5, -1)
                    session_goal = client.hget(state_key, "goal") or ""
                    
                    try:
                        session_goal = client.hget(state_key, "goal") or ""
                        
                        try:
                            print(f"DEBUG: Calling Gemini extraction...")
                            recent_summaries_decoded = [s.decode() if isinstance(s, bytes) else s for s in recent_summaries]
                            
                            extraction = memory_writer.extract_memories(
                                user_message=user_msg,
                                assistant_message=asst_msg,
                                session_goal=session_goal,
                                recent_summaries=recent_summaries_decoded
                            )
                            print(f"DEBUG: Extraction complete: {len(extraction.get('candidates', []))} candidates")
                            
                            session_summary = extraction.get("session_summary")
                            if session_summary:
                                if isinstance(session_summary, list):
                                    session_summary = "\n".join(session_summary)
                                client.rpush(summaries_key, session_summary)
                                client.ltrim(summaries_key, -20, -1)
                                print(f"DEBUG: Updated session summary")
                            
                            if extraction.get("safety", {}).get("store_allowed", True):
                                for candidate in extraction.get("candidates", []):
                                    confidence = candidate.get("confidence", 0)
                                    print(f"DEBUG: Candidate confidence: {confidence}")
                                    if confidence < 0.75:
                                        print(f"DEBUG: Skipping candidate (low confidence)")
                                        continue
                                    
                                    dedupe_key = candidate.get("dedupe_key", "")
                                    if dedupe_key:
                                        dedupe_redis_key = f"user:{user_id}:dedupe:{dedupe_key}"
                                        if client.exists(dedupe_redis_key):
                                            print(f"DEBUG: Skipping candidate (duplicate)")
                                            continue
                                        
                                        print(f"DEBUG: Writing memory to Weaviate...")
                                        write_memory_to_weaviate(user_id, candidate)
                                        client.setex(dedupe_redis_key, 2592000, "1")
                                        print(f"DEBUG: Memory written successfully")
                                    else:
                                        write_memory_to_weaviate(user_id, candidate)
                            else:
                                print(f"DEBUG: Storage not allowed: {extraction.get('safety', {}).get('reason')}")
                        
                        except Exception as e:
                            print(f"ERROR: Memory extraction failed: {e}")
                            import traceback
            
        return {"ingested": ingested_count}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest events: {str(e)}"
        )
