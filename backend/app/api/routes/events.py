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
from app.services.safety_gate import safety_gate
from app.services.critic import critic
from app.services.reward import reward_resolver

# Sprint 15: New imports for Redis Streams
USE_STREAMS = True  # Feature flag for gradual rollout


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
            
            # Sprint 13.1: Safety Gate for USER_MESSAGE (BEFORE storage)
            if canonical.event_type == "USER_MESSAGE":
                text = canonical.payload.get("text", "")
                
                # Call safety gate
                safety_result = await safety_gate(text)
                canonical.payload["safety_result"] = safety_result.model_dump()
                
                if not safety_result.allowed:
                    # BLOCKED: only increment counter, no storage
                    print(f"[SAFETY_GATE] BLOCKED: {safety_result.category} - {safety_result.reason_short}")
                    
                    # Increment safety counter
                    counter_key = f"safety_counter:{canonical.user_id}:{safety_result.category}"
                    client.incr(counter_key)
                    client.expire(counter_key, 7 * 24 * 60 * 60)  # 7 days TTL
                    
                    # DO NOT add to canonical_events (no storage)
                    continue
                
                # Compute fingerprint
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
                
                # Sprint 13.3: Reward evaluation for previous attempt
                # When new USER_MESSAGE arrives, evaluate the previous AI_RESPONSE
                if attempt_count > 1:
                    # Get previous attempts
                    records = attempt_thread_manager.get_attempt_records(attempt_thread_id, limit=10)
                    
                    if len(records) > 0:
                        # Get previous attempt (most recent before this)
                        prev_record = records[0]
                        prev_fingerprint = prev_record.get("payload", {}).get("fingerprint")
                        prev_ts_ms = prev_record.get("ts_ms")
                        prev_attempt_id = prev_record.get("attempt_id")
                        
                        # Compute reward
                        reward_result = reward_resolver(
                            new_message=text,
                            new_fingerprint=fingerprint,
                            previous_fingerprint=prev_fingerprint,
                            previous_timestamp_ms=prev_ts_ms
                        )
                        
                        # Update previous attempt record with reward
                        attempt_thread_manager.update_attempt_record_reward(
                            attempt_thread_id=attempt_thread_id,
                            attempt_id=prev_attempt_id,
                            reward=reward_result.reward,
                            outcome=reward_result.outcome
                        )
                        
                        print(f"[REWARD] Previous attempt: reward={reward_result.reward}, outcome={reward_result.outcome}, reason={reward_result.reason}")
                        
                        # Update best attempt if eligible
                        prev_critic_score = prev_record.get("critic_score", 0.0)
                        became_best = attempt_thread_manager.update_best_attempt(
                            attempt_thread_id=attempt_thread_id,
                            attempt_id=prev_attempt_id,
                            reward=reward_result.reward,
                            critic_score=prev_critic_score,
                            outcome=reward_result.outcome
                        )
                        
                        if became_best:
                            print(f"[BEST_ATTEMPT] New best: {prev_attempt_id[:8]}...")
                
                # Add attempt record (initial, will be updated with critic score later)
                attempt_thread_manager.add_attempt_record(
                    attempt_thread_id=attempt_thread_id,
                    attempt_id=attempt_id,
                    event_id=canonical.event_id,
                    trace_id=canonical.trace_id,
                    payload=canonical.payload,
                    reward=0.0,  # Will be updated when next message arrives
                    critic_score=0.0,  # Will be updated when AI_RESPONSE arrives
                    outcome="unknown"
                )
                
                print(f"[ATTEMPT] USER_MESSAGE fingerprint={fingerprint[:8]}... thread={attempt_thread_id[:8]}... count={attempt_count}")
            
            # Sprint 13.2: Critic scoring for AI_RESPONSE
            elif canonical.event_type == "AI_RESPONSE":
                # Find paired USER_MESSAGE in same trace
                user_msg_text = None
                user_attempt_id = None
                user_thread_id = None
                
                for c in canonical_events:
                    if c.trace_id == canonical.trace_id and c.event_type == "USER_MESSAGE":
                        user_msg_text = c.payload.get("text", "")
                        user_attempt_id = c.payload.get("attempt_id")
                        user_thread_id = c.attempt_thread_id
                        break
                
                if user_msg_text:
                    assistant_text = canonical.payload.get("text", "")
                    
                    # Call critic to score response
                    critic_result = await critic(
                        user_text=user_msg_text,
                        assistant_text=assistant_text
                    )
                    
                    canonical.payload["critic_result"] = critic_result.model_dump()
                    canonical.attempt_thread_id = user_thread_id  # Link to same thread
                    
                    # Update the USER_MESSAGE attempt record with critic score
                    if user_attempt_id and user_thread_id:
                        records = attempt_thread_manager.get_attempt_records(user_thread_id, limit=10)
                        for record in records:
                            if record.get("attempt_id") == user_attempt_id:
                                # Update record with critic score
                                record["critic_score"] = critic_result.critic_score
                                record["violations"] = critic_result.violations
                                # This is a simplified update - in production, use a proper update method
                                break
                    
                    print(f"[CRITIC] Score={critic_result.critic_score:.2f}, violations={critic_result.violations}")
                else:
                    canonical.attempt_thread_id = canonical.trace_id
            
            # For other event types, set attempt_thread_id to trace_id
            elif canonical.attempt_thread_id == "":
                canonical.attempt_thread_id = canonical.trace_id
            
            canonical_events.append(canonical)
        
        # Second pass: store canonical events (only if allowed)
        for canonical in canonical_events:
            # Sprint 15.1: Write to Redis Streams (replayable, ordered)
            if USE_STREAMS:
                stream_key = f"stream:events:{canonical.user_id}"
                
                # Prepare event data for stream
                stream_data = canonical.model_dump()
                # Convert payload dict to JSON string for stream storage
                stream_data['payload'] = json.dumps(stream_data['payload'])
                
                # XADD stream:events:{user_id} * <fields>
                try:
                    message_id = client.xadd(stream_key, stream_data, maxlen=1000)
                    print(f"[STREAM] Added event {canonical.event_id[:8]}... to stream {message_id}")
                except Exception as e:
                    print(f"[STREAM] Error writing to stream: {e}")
            
            # Keep LPUSH for backward compatibility and debugging
            events_key = f"events:{canonical.user_id}:{canonical.provider}"
            canonical_json = canonical.model_dump_json()
            client.lpush(events_key, canonical_json)
            
            # Keep only last 50 events
            client.ltrim(events_key, 0, 49)
            
            # Set TTL to 24 hours
            client.expire(events_key, 24 * 60 * 60)
            
            # Update session state
            state_key = f"session:{canonical.user_id}:state"
            state_updates = {
                "last_event_ts": str(canonical.ts_ms),
                "last_provider": canonical.provider,
                "last_event_type": canonical.event_type
            }
            if canonical.payload.get("url"):
                state_updates["last_url"] = canonical.payload["url"]
            
            client.hset(state_key, mapping=state_updates)
            client.expire(state_key, 24 * 60 * 60)
            
            ingested_count += 1
        
        return {"ingested": ingested_count}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest events: {str(e)}"
        )
