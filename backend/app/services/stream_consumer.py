"""
Redis Streams Consumer for Canonical Events (Sprint 15.1)

Replaces fragile LPUSH lists with replayable, ordered event pipeline.
All business logic (safety, attempts, reward) runs here, not in API routes.
"""

import json
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from app.services.redis_client import redis_client
from app.schemas.canonical import CanonicalEvent
from app.services.attempt_thread import attempt_thread_manager
from app.services.safety_gate import safety_gate
from app.services.critic import critic
from app.services.reward import reward_resolver


class StreamConsumer:
    """
    Consumes canonical events from Redis Streams.
    
    Stream key: stream:events:{user_id}
    Consumer group: cg:processor
    Consumer name: processor-1
    """
    
    def __init__(self):
        self.client = redis_client.client
        self.consumer_group = "cg:processor"
        self.consumer_name = "processor-1"
        self.running = False
    
    def ensure_consumer_group(self, stream_key: str):
        """Create consumer group if it doesn't exist"""
        try:
            # Try to create consumer group
            self.client.xgroup_create(
                name=stream_key,
                groupname=self.consumer_group,
                id='0',
                mkstream=True
            )
        except Exception as e:
            # Group already exists, that's fine
            if "BUSYGROUP" not in str(e):
                print(f"[STREAM] Consumer group setup: {e}")
    
    async def process_event(self, event_data: Dict[str, Any]) -> bool:
        """
        Process a single canonical event.
        
        This is where ALL business logic runs:
        - Safety gate
        - Critic scoring
        - Reward evaluation
        - Attempt tracking
        - Best-attempt selection
        
        Args:
            event_data: Canonical event fields from stream
            
        Returns:
            True if processed successfully, False if should retry
        """
        try:
            # Reconstruct CanonicalEvent from stream data
            canonical = CanonicalEvent(**event_data)
            
            # Sprint 13.1: Safety Gate for USER_MESSAGE
            if canonical.event_type == "USER_MESSAGE":
                text = canonical.payload.get("text", "")
                
                # Check if already processed (has safety_result)
                if "safety_result" not in canonical.payload:
                    safety_result = await safety_gate(text)
                    canonical.payload["safety_result"] = safety_result.model_dump()
                    
                    if not safety_result.allowed:
                        # BLOCKED: increment counter only
                        print(f"[STREAM] BLOCKED: {safety_result.category} - {safety_result.reason_short}")
                        counter_key = f"safety_counter:{canonical.user_id}:{safety_result.category}"
                        self.client.incr(counter_key)
                        self.client.expire(counter_key, 7 * 24 * 60 * 60)
                        
                        # Increment metrics
                        self.client.incr(f"metrics:blocked_requests:{canonical.user_id}")
                        
                        return True  # Successfully processed (blocked)
                
                # Sprint 13.3: Reward evaluation for previous attempt
                attempt_thread_id = canonical.attempt_thread_id
                if attempt_thread_id:
                    attempt_id = canonical.payload.get("attempt_id")
                    fingerprint = canonical.payload.get("fingerprint", "")
                    
                    # Get previous attempts
                    records = attempt_thread_manager.get_attempt_records(attempt_thread_id, limit=10)
                    
                    if len(records) > 1:  # Has previous attempt
                        prev_record = records[1]  # Second most recent (first is current)
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
                        
                        # Update previous attempt with reward
                        attempt_thread_manager.update_attempt_record_reward(
                            attempt_thread_id=attempt_thread_id,
                            attempt_id=prev_attempt_id,
                            reward=reward_result.reward,
                            outcome=reward_result.outcome
                        )
                        
                        print(f"[STREAM_REWARD] reward={reward_result.reward}, outcome={reward_result.outcome}")
                        
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
                            print(f"[STREAM_BEST] New best attempt in thread {attempt_thread_id[:8]}...")
                            # Increment metrics
                            self.client.incr(f"metrics:resolved_threads:{canonical.user_id}")
            
            # Sprint 13.2: Critic scoring for AI_RESPONSE
            elif canonical.event_type == "AI_RESPONSE":
                critic_result_data = canonical.payload.get("critic_result")
                if critic_result_data:
                    # Already has critic score, update the attempt record
                    attempt_thread_id = canonical.attempt_thread_id
                    user_attempt_id = canonical.payload.get("linked_attempt_id")
                    
                    if attempt_thread_id and user_attempt_id:
                        # Find and update the USER_MESSAGE attempt record
                        records = attempt_thread_manager.get_attempt_records(attempt_thread_id, limit=10)
                        for record in records:
                            if record.get("attempt_id") == user_attempt_id:
                                critic_score = critic_result_data.get("critic_score", 0.5)
                                # Update via Redis (simplified - in production use proper update)
                                break
            
            # Store in events list (for backward compatibility and debugging)
            events_key = f"events:{canonical.user_id}:{canonical.provider}"
            canonical_json = canonical.model_dump_json()
            self.client.lpush(events_key, canonical_json)
            self.client.ltrim(events_key, 0, 49)  # Keep last 50
            self.client.expire(events_key, 24 * 60 * 60)  # 24 hours
            
            # Update session state
            state_key = f"session:{canonical.user_id}:state"
            state_updates = {
                "last_event_ts": str(canonical.ts_ms),
                "last_provider": canonical.provider,
                "last_event_type": canonical.event_type
            }
            self.client.hset(state_key, mapping=state_updates)
            self.client.expire(state_key, 24 * 60 * 60)
            
            # Increment metrics
            self.client.incr(f"metrics:attempts:{canonical.user_id}")
            
            print(f"[STREAM] Processed {canonical.event_type} for user {canonical.user_id[:8]}...")
            return True
            
        except Exception as e:
            print(f"[STREAM] Error processing event: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def consume_stream(self, user_id: str, max_count: int = 10):
        """
        Consume events from a user's stream.
        
        Args:
            user_id: User identifier
            max_count: Maximum messages to read per call
        """
        stream_key = f"stream:events:{user_id}"
        
        # Ensure consumer group exists
        self.ensure_consumer_group(stream_key)
        
        try:
            # Read messages from stream
            # XREADGROUP GROUP cg:processor processor-1 COUNT 10 BLOCK 2000 STREAMS stream:events:{user_id} >
            messages = self.client.xreadgroup(
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                streams={stream_key: '>'},
                count=max_count,
                block=2000  # 2 seconds
            )
            
            if not messages:
                return 0
            
            processed_count = 0
            for stream, msgs in messages:
                for msg_id, fields in msgs:
                    # Convert bytes to strings
                    event_data = {
                        k.decode('utf-8') if isinstance(k, bytes) else k:
                        v.decode('utf-8') if isinstance(v, bytes) else v
                        for k, v in fields.items()
                    }
                    
                    # Parse JSON fields
                    if 'payload' in event_data:
                        event_data['payload'] = json.loads(event_data['payload'])
                    
                    # Process event
                    success = await self.process_event(event_data)
                    
                    if success:
                        # Acknowledge message
                        self.client.xack(stream_key, self.consumer_group, msg_id)
                        processed_count += 1
                    else:
                        print(f"[STREAM] Failed to process message {msg_id}, will retry")
            
            return processed_count
            
        except Exception as e:
            print(f"[STREAM] Error consuming stream: {e}")
            return 0
    
    async def run_forever(self, user_ids: List[str]):
        """
        Run consumer loop for multiple users.
        
        Args:
            user_ids: List of user IDs to monitor
        """
        self.running = True
        print(f"[STREAM] Starting consumer for {len(user_ids)} users...")
        
        while self.running:
            try:
                for user_id in user_ids:
                    count = await self.consume_stream(user_id)
                    if count > 0:
                        print(f"[STREAM] Processed {count} events for user {user_id[:8]}...")
                
                # Brief pause between cycles
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"[STREAM] Consumer loop error: {e}")
                await asyncio.sleep(1)
    
    def stop(self):
        """Stop the consumer loop"""
        self.running = False


# Global instance
stream_consumer = StreamConsumer()
