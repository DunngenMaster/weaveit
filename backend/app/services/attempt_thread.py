from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, Any
import json
from app.services.redis_client import redis_client


class AttemptThreadManager:
    """
    Manages attempt threads for tracking repeated user requests and their outcomes.
    
    Redis keys:
    - attempt_index:{user_id}:{fingerprint} -> attempt_thread_id (string)
    - attempt:{attempt_thread_id} (hash with metadata)
    - attempt:{attempt_thread_id}:records (list of attempt records)
    """
    
    def __init__(self):
        self.client = redis_client.client
        self.ttl_seconds = 30 * 24 * 60 * 60  # 30 days
    
    def get_or_create_thread(
        self, 
        user_id: str, 
        fingerprint: str, 
        domain: str = "unknown"
    ) -> tuple[str, int]:
        """
        Get existing attempt thread or create new one.
        
        Args:
            user_id: User identifier
            fingerprint: Message fingerprint (sha256)
            domain: Domain/category (default "unknown")
            
        Returns:
            Tuple of (attempt_thread_id, attempt_count)
        """
        
        index_key = f"attempt_index:{user_id}:{fingerprint}"
        
        # Check if thread already exists
        attempt_thread_id = self.client.get(index_key)
        
        if attempt_thread_id:
            # Thread exists, increment attempt count
            attempt_thread_id = attempt_thread_id.decode('utf-8') if isinstance(attempt_thread_id, bytes) else attempt_thread_id
            thread_key = f"attempt:{attempt_thread_id}"
            
            # Increment attempt_count
            attempt_count = self.client.hincrby(thread_key, "attempt_count", 1)
            
            # Update timestamp
            self.client.hset(thread_key, "updated_ts_ms", int(datetime.now().timestamp() * 1000))
            
            # Refresh TTL
            self.client.expire(thread_key, self.ttl_seconds)
            self.client.expire(index_key, self.ttl_seconds)
            
            return attempt_thread_id, attempt_count
        
        else:
            # Create new thread
            attempt_thread_id = str(uuid4())
            thread_key = f"attempt:{attempt_thread_id}"
            records_key = f"{thread_key}:records"
            
            now_ms = int(datetime.now().timestamp() * 1000)
            
            # Set index
            self.client.set(index_key, attempt_thread_id, ex=self.ttl_seconds)
            
            # Create thread metadata
            thread_data = {
                "user_id": user_id,
                "fingerprint": fingerprint,
                "domain": domain,
                "attempt_count": 1,
                "status": "open",
                "best_reward": -999.0,
                "created_ts_ms": now_ms,
                "updated_ts_ms": now_ms
            }
            
            self.client.hset(thread_key, mapping=thread_data)
            self.client.expire(thread_key, self.ttl_seconds)
            
            # Initialize empty records list (will be populated later)
            self.client.expire(records_key, self.ttl_seconds)
            
            return attempt_thread_id, 1
    
    def add_attempt_record(
        self, 
        attempt_thread_id: str, 
        attempt_id: str,
        event_id: str,
        trace_id: str,
        payload: Dict[str, Any],
        reward: float = 0.0,
        critic_score: float = 0.0,
        outcome: str = "unknown"
    ) -> None:
        """
        Add an attempt record to the thread.
        
        Args:
            attempt_thread_id: The thread this attempt belongs to
            attempt_id: Unique ID for this specific attempt
            event_id: The canonical event ID
            trace_id: The trace ID linking request/response
            payload: The event payload
            reward: Reward score for this attempt (default 0.0)
            critic_score: Critic quality score (default 0.0)
            outcome: Outcome type: success, fail, unknown
        """
        
        records_key = f"attempt:{attempt_thread_id}:records"
        
        record = {
            "attempt_id": attempt_id,
            "event_id": event_id,
            "trace_id": trace_id,
            "ts_ms": int(datetime.now().timestamp() * 1000),
            "payload": payload,
            "reward": reward,
            "critic_score": critic_score,
            "outcome": outcome
        }
        
        # Store as JSON in list
        self.client.lpush(records_key, json.dumps(record))
        self.client.expire(records_key, self.ttl_seconds)
    
    def get_thread_metadata(self, attempt_thread_id: str) -> Optional[Dict[str, Any]]:
        """Get attempt thread metadata"""
        thread_key = f"attempt:{attempt_thread_id}"
        data = self.client.hgetall(thread_key)
        
        if not data:
            return None
        
        # Convert bytes to strings
        return {
            k.decode('utf-8') if isinstance(k, bytes) else k: 
            v.decode('utf-8') if isinstance(v, bytes) else v 
            for k, v in data.items()
        }
    
    def get_attempt_records(self, attempt_thread_id: str, limit: int = 10) -> list[Dict[str, Any]]:
        """
        Get attempt records for a thread.
        
        Args:
            attempt_thread_id: The thread ID
            limit: Maximum number of records to return
            
        Returns:
            List of attempt records (most recent first)
        """
        records_key = f"attempt:{attempt_thread_id}:records"
        records_json = self.client.lrange(records_key, 0, limit - 1)
        
        return [json.loads(r) for r in records_json]
    
    def update_attempt_record_reward(
        self,
        attempt_thread_id: str,
        attempt_id: str,
        reward: float,
        outcome: str
    ) -> bool:
        """
        Update the reward and outcome for a specific attempt record.
        
        This is called when a new USER_MESSAGE arrives to evaluate
        the previous AI_RESPONSE in the thread.
        
        Args:
            attempt_thread_id: The thread ID
            attempt_id: The specific attempt to update
            reward: The computed reward score
            outcome: The outcome (success, fail, unknown)
            
        Returns:
            True if record was found and updated, False otherwise
        """
        records_key = f"attempt:{attempt_thread_id}:records"
        
        # Get all records
        records_json = self.client.lrange(records_key, 0, -1)
        records = [json.loads(r) for r in records_json]
        
        # Find and update the target record
        updated = False
        for i, record in enumerate(records):
            if record.get("attempt_id") == attempt_id:
                record["reward"] = reward
                record["outcome"] = outcome
                # Update in Redis (replace at index)
                self.client.lset(records_key, i, json.dumps(record))
                updated = True
                break
        
        return updated
    
    def update_best_attempt(
        self, 
        attempt_thread_id: str, 
        attempt_id: str, 
        reward: float,
        critic_score: float,
        outcome: str
    ) -> bool:
        """
        Update the best attempt for a thread using eligibility rules.
        
        Best-attempt selection logic:
        - final_score = 0.7 * reward + 0.3 * critic_score
        - Eligible only if: outcome=="success" AND critic_score>=0.8 AND reward>=0.6
        - Thread status becomes "resolved" when a success is found
        
        Args:
            attempt_thread_id: The thread ID
            attempt_id: The attempt that achieved this reward
            reward: The reward score
            critic_score: The critic quality score
            outcome: The outcome type (success, fail, unknown)
            
        Returns:
            True if this became the new best attempt, False otherwise
        """
        
        thread_key = f"attempt:{attempt_thread_id}"
        
        # Check eligibility
        is_eligible = (
            outcome == "success" and 
            critic_score >= 0.8 and 
            reward >= 0.6
        )
        
        if not is_eligible:
            return False
        
        # Compute final score
        final_score = 0.7 * reward + 0.3 * critic_score
        
        # Get current best final_score
        current_best_score = self.client.hget(thread_key, "best_final_score")
        current_best_score = float(current_best_score) if current_best_score else -999.0
        
        # Update if this is better
        if final_score > current_best_score:
            self.client.hset(thread_key, "best_attempt_id", attempt_id)
            self.client.hset(thread_key, "best_reward", reward)
            self.client.hset(thread_key, "best_critic_score", critic_score)
            self.client.hset(thread_key, "best_final_score", final_score)
            self.client.hset(thread_key, "status", "resolved")  # Thread is now resolved
            self.client.hset(thread_key, "updated_ts_ms", int(datetime.now().timestamp() * 1000))
            return True
        
        return False


# Global instance
attempt_thread_manager = AttemptThreadManager()
