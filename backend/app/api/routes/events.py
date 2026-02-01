import json
import hashlib
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, status
from app.schemas.events import EventBatch
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client
from app.services.memory_writer import memory_writer


router = APIRouter(prefix="/v1/events")


def normalize_text(text: str) -> str:
    return text.lower().strip()


def compute_fingerprint(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode()).hexdigest()


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
        
        for event in batch.events:
            session_id = event.session_id
            user_id = event.user_id
            
            event_key = f"events:{session_id}"
            event_json = event.model_dump_json()
            client.rpush(event_key, event_json)
            client.expire(event_key, 86400)
            
            state_key = f"session:{session_id}:state"
            state_updates = {
                "last_event_ts": str(event.ts),
                "last_provider": event.provider
            }
            if event.url:
                state_updates["last_url"] = event.url
            
            client.hset(state_key, mapping=state_updates)
            client.expire(state_key, 21600)
            
            if event.event_type == "CHAT_TURN":
                summaries_key = f"session:{session_id}:summaries"
                client.rpush(summaries_key, "TURN_RECEIVED")
                client.ltrim(summaries_key, -20, -1)
                
                if event.payload and "message" in event.payload:
                    message = event.payload["message"]
                    fingerprint = compute_fingerprint(message)
                    attempts_key = f"user:{user_id}:attempts:{fingerprint}"
                    client.incr(attempts_key)
                    client.expire(attempts_key, 86400)
                
                print(f"DEBUG: CHAT_TURN detected, payload keys: {event.payload.keys() if event.payload else 'None'}")
                
                if event.payload and "user_message" in event.payload and "assistant_message" in event.payload:
                    print(f"DEBUG: Starting memory extraction for user {user_id}")
                    user_msg = event.payload["user_message"]
                    asst_msg = event.payload["assistant_message"]
                    
                    recent_summaries = client.lrange(summaries_key, -5, -1)
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
                        traceback.print_exc()
            
            ingested_count += 1
        
        return {"ingested": ingested_count}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest events: {str(e)}"
        )
