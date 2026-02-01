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
    Consumes canonical events from Redis Streams with retry + DLQ.
    
    Stream key: stream:events:{user_id}
    DLQ key: stream:dlq:{user_id}
    Retry tracking: retry:{stream_entry_id}
    Consumer group: cg:processor
    Consumer name: processor-1
    
    Sprint 17.2:
    - Retry counter per message (max 3 attempts)
    - DLQ stream for failed messages with error reason + stack trace
    - AUTOCLAIM for stuck messages (consumer crashes)
    """
    
    def __init__(self, max_retries: int = 3):
        self.client = redis_client.client
        self.consumer_group = "cg:processor"
        self.consumer_name = "processor-1"
        self.max_retries = max_retries
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
    
    def get_retry_count(self, message_id: str) -> int:
        """Get current retry count for a message"""
        retry_key = f"retry:{message_id}"
        count = self.client.get(retry_key)
        return int(count) if count else 0
    
    def increment_retry(self, message_id: str) -> int:
        """Increment retry counter and return new count"""
        retry_key = f"retry:{message_id}"
        new_count = self.client.incr(retry_key)
        self.client.expire(retry_key, 24 * 60 * 60)  # 24 hours TTL
        return new_count
    
    def move_to_dlq(self, user_id: str, message_id: str, event_data: Dict[str, Any], error_msg: str):
        """
        Move failed message to Dead Letter Queue.
        
        DLQ entry includes:
        - Original message data
        - Error reason
        - Stack trace
        - Retry count
        - Timestamp
        """
        dlq_key = f"stream:dlq:{user_id}"
        retry_count = self.get_retry_count(message_id)
        
        dlq_data = {
            'original_message_id': message_id,
            'retry_count': str(retry_count),
            'error': error_msg,
            'failed_at': datetime.now().isoformat(),
            'event_data': json.dumps(event_data)
        }
        
        try:
            dlq_message_id = self.client.xadd(dlq_key, dlq_data, maxlen=500)  # Keep last 500 DLQ entries
            print(f"[DLQ] Moved message {message_id} to DLQ: {dlq_message_id}")
            
            # Increment DLQ counter
            self.client.incr(f"metrics:dlq_count:{user_id}")
        except Exception as e:
            print(f"[DLQ] Error writing to DLQ: {e}")
    
    async def autoclaim_pending(self, stream_key: str, min_idle_time_ms: int = 60000):
        """
        Use AUTOCLAIM to recover stuck messages (consumer crashes).
        
        Args:
            stream_key: Stream to check for pending messages
            min_idle_time_ms: Minimum idle time in ms (default 60s)
        """
        try:
            # AUTOCLAIM stream group consumer min_idle_time_ms 0-0 COUNT 10
            result = self.client.xautoclaim(
                name=stream_key,
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                min_idle_time=min_idle_time_ms,
                start_id='0-0',
                count=10
            )
            
            if result and len(result) > 1:
                claimed_messages = result[1]
                if claimed_messages:
                    print(f"[AUTOCLAIM] Claimed {len(claimed_messages)} stuck messages from {stream_key}")
                    return claimed_messages
            
            return []
        except Exception as e:
            print(f"[AUTOCLAIM] Error: {e}")
            return []
        """
        Process a single canonical event with error tracking.
        
        This is where ALL business logic runs:
        - Safety gate
        - Critic scoring
        - Reward evaluation
        - Attempt tracking
        - Best-attempt selection
        
        Args:
            event_data: Canonical event fields from stream
            message_id: Stream message ID for retry tracking
            user_id: User ID for DLQ routing
            
        Returns:
            (success: bool, error_msg: str) - True if processed successfully, False if should retry
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
            return True, ""
            
        except Exception as e:
            error_msg = str(e)
            print(f"[STREAM] Error processing event: {error_msg}")
            import traceback
            stack_trace = traceback.format_exc()
            return False, f"{error_msg}\n\n{stack_trace}"
    
    async def consume_stream(self, user_id: str, max_count: int = 10):
        """
        Consume events from a user's stream with retry + DLQ support.
        
        Args:
            user_id: User identifier
            max_count: Maximum messages to read per call
        """
        stream_key = f"stream:events:{user_id}"
        
        # Ensure consumer group exists
        self.ensure_consumer_group(stream_key)
        
        # First, try to autoclaim any stuck messages (>60s idle)
        stuck_messages = await self.autoclaim_pending(stream_key, min_idle_time_ms=60000)
        if stuck_messages:
            print(f"[STREAM] Processing {len(stuck_messages)} autoclaimed messages")
            await self._process_messages(user_id, stream_key, stuck_messages)
        
        try:
            # Read new messages from stream
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
                processed_count += await self._process_messages(user_id, stream_key, msgs)
            
            return processed_count
            
        except Exception as e:
            print(f"[STREAM] Error consuming stream: {e}")
            return 0
    
    async def _process_messages(self, user_id: str, stream_key: str, msgs: List) -> int:
        """
        Process a batch of messages with retry logic.
        
        Returns:
            Number of successfully processed messages
        """
        processed_count = 0
        
        for msg_id, fields in msgs:
            # Convert bytes to strings
            event_data = {
                k.decode('utf-8') if isinstance(k, bytes) else k:
                v.decode('utf-8') if isinstance(v, bytes) else v
                for k, v in fields.items()
            }
            
            # Parse JSON fields
            if 'payload' in event_data:
                try:
                    event_data['payload'] = json.loads(event_data['payload'])
                except json.JSONDecodeError:
                    print(f"[STREAM] Invalid JSON in payload for message {msg_id}")
                    continue
            
            # Check retry count
            retry_count = self.get_retry_count(msg_id)
            
            if retry_count >= self.max_retries:
                # Max retries exceeded, move to DLQ
                error_msg = f"Max retries ({self.max_retries}) exceeded"
                self.move_to_dlq(user_id, msg_id, event_data, error_msg)
                
                # Acknowledge to remove from pending
                self.client.xack(stream_key, self.consumer_group, msg_id)
                continue
            
            # Process event
            success, error_msg = await self.process_event(event_data, msg_id, user_id)
            
            if success:
                # Acknowledge message
                self.client.xack(stream_key, self.consumer_group, msg_id)
                processed_count += 1
            else:
                # Increment retry counter
                new_retry_count = self.increment_retry(msg_id)
                print(f"[STREAM] Failed to process message {msg_id}, retry count: {new_retry_count}/{self.max_retries}")
                
                if new_retry_count >= self.max_retries:
                    # Move to DLQ on next iteration
                    self.move_to_dlq(user_id, msg_id, event_data, error_msg)
                    self.client.xack(stream_key, self.consumer_group, msg_id)
        
        return processed_count
    
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


# Global instance (max 3 retries before DLQ)
stream_consumer = StreamConsumer(max_retries=3)
