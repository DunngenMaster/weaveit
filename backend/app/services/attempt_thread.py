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
        payload: Dict[str, Any]
    ) -> None:
        """
        Add an attempt record to the thread.
        
        Args:
            attempt_thread_id: The thread this attempt belongs to
            attempt_id: Unique ID for this specific attempt
            event_id: The canonical event ID
            trace_id: The trace ID linking request/response
            payload: The event payload
        """
        
        records_key = f"attempt:{attempt_thread_id}:records"
        
        record = {
            "attempt_id": attempt_id,
            "event_id": event_id,
            "trace_id": trace_id,
            "ts_ms": int(datetime.now().timestamp() * 1000),
            "payload": payload
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
    
    def update_best_attempt(
        self, 
        attempt_thread_id: str, 
        attempt_id: str, 
        reward: float
    ) -> None:
        """
        Update the best attempt for a thread based on reward score.
        
        Args:
            attempt_thread_id: The thread ID
            attempt_id: The attempt that achieved this reward
            reward: The reward score
        """
        
        thread_key = f"attempt:{attempt_thread_id}"
        
        # Get current best reward
        current_best = self.client.hget(thread_key, "best_reward")
        current_best = float(current_best) if current_best else -999.0
        
        # Update if this is better
        if reward > current_best:
            self.client.hset(thread_key, "best_attempt_id", attempt_id)
            self.client.hset(thread_key, "best_reward", reward)
            self.client.hset(thread_key, "updated_ts_ms", int(datetime.now().timestamp() * 1000))


# Global instance
attempt_thread_manager = AttemptThreadManager()
