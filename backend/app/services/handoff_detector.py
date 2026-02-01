"""
Story 18.5: Handoff Detector - Detect when CSA generation is needed

Triggers CSA creation when:
1. attempt_count >= 5 for same fingerprint in 30 minutes
2. rolling summaries length >= 15
3. new provider detected (provider change)
4. explicit handoff phrases in USER_MESSAGE
"""

import time
import json
from typing import Optional
from app.services.redis_client import redis_client
from app.services.attempt_thread import attempt_thread_manager


HANDOFF_PHRASES = [
    "continue this",
    "new chat",
    "hanging",
    "start new chat",
    "switch to",
    "move to",
    "can you continue",
    "keep going",
    "resume this",
    "pick up where"
]


class HandoffDetector:
    """Detects when conversation handoff is needed and triggers CSA generation."""
    
    def __init__(self):
        self.redis = redis_client
    
    def check_handoff_needed(
        self,
        user_id: str,
        current_provider: str,
        text: Optional[str] = None,
        fingerprint: Optional[str] = None
    ) -> bool:
        """
        Check if handoff is needed based on multiple signals.
        
        Args:
            user_id: User identifier
            current_provider: Current provider (chatgpt/claude/gemini)
            text: Message text (for explicit handoff detection)
            fingerprint: Message fingerprint (for attempt counting)
            
        Returns:
            True if handoff is needed
        """
        # Check if already flagged
        handoff_flag = f"handoff_required:{user_id}"
        if self.redis.client.get(handoff_flag):
            return True  # Already detected
        
        # Signal 1: High attempt count (same problem repeated >= 5 times)
        if fingerprint and self._check_high_attempt_count(user_id, fingerprint):
            print(f"[HANDOFF] High attempt count detected for user {user_id}")
            self._set_handoff_flag(user_id)
            return True
        
        # Signal 2: Long session (>= 15 summaries)
        if self._check_long_session(user_id):
            print(f"[HANDOFF] Long session detected for user {user_id}")
            self._set_handoff_flag(user_id)
            return True
        
        # Signal 3: Provider change
        if self._check_provider_change(user_id, current_provider):
            print(f"[HANDOFF] Provider change detected for user {user_id}")
            self._set_handoff_flag(user_id)
            return True
        
        # Signal 4: Explicit handoff phrase
        if text and self._check_explicit_handoff(text):
            print(f"[HANDOFF] Explicit handoff phrase detected for user {user_id}")
            self._set_handoff_flag(user_id)
            return True
        
        return False
    
    def _check_high_attempt_count(self, user_id: str, fingerprint: str) -> bool:
        """Check if attempt count >= 5 for same fingerprint in 30 minutes."""
        try:
            thread_id = f"thread:{fingerprint}:{user_id}"
            thread_data = self.redis.client.hgetall(thread_id)
            
            if not thread_data:
                return False
            
            attempt_count = int(thread_data.get('attempt_count', 0))
            created_ts_ms = int(thread_data.get('created_ts_ms', 0))
            now_ms = int(time.time() * 1000)
            time_diff_minutes = (now_ms - created_ts_ms) / 1000 / 60
            
            # >= 5 attempts in last 30 minutes
            return attempt_count >= 5 and time_diff_minutes <= 30
            
        except Exception as e:
            print(f"[HANDOFF] Error checking attempt count: {e}")
            return False
    
    def _check_long_session(self, user_id: str) -> bool:
        """Check if session has >= 15 rolling summaries."""
        try:
            summaries_key = f"summaries:{user_id}"
            summaries_count = self.redis.client.llen(summaries_key)
            return summaries_count >= 15
            
        except Exception as e:
            print(f"[HANDOFF] Error checking session length: {e}")
            return False
    
    def _check_provider_change(self, user_id: str, current_provider: str) -> bool:
        """Check if provider changed from last session."""
        try:
            last_provider_key = f"last_provider:{user_id}"
            last_provider = self.redis.client.get(last_provider_key)
            
            if not last_provider:
                # First session, store current provider
                self.redis.client.setex(last_provider_key, 24 * 60 * 60, current_provider)
                return False
            
            last_provider_str = last_provider.decode() if isinstance(last_provider, bytes) else last_provider
            
            # Provider changed (e.g., chatgpt -> claude)
            if last_provider_str != current_provider:
                # Update to new provider
                self.redis.client.setex(last_provider_key, 24 * 60 * 60, current_provider)
                return True
            
            return False
            
        except Exception as e:
            print(f"[HANDOFF] Error checking provider change: {e}")
            return False
    
    def _check_explicit_handoff(self, text: str) -> bool:
        """Check if text contains explicit handoff phrases."""
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in HANDOFF_PHRASES)
    
    def _set_handoff_flag(self, user_id: str):
        """Set handoff required flag in Redis (TTL 2 hours)."""
        handoff_flag = f"handoff_required:{user_id}"
        self.redis.client.setex(handoff_flag, 2 * 60 * 60, "true")
        print(f"[HANDOFF] Set handoff_required flag for user {user_id}")
    
    def clear_handoff_flag(self, user_id: str):
        """Clear handoff flag after CSA is generated."""
        handoff_flag = f"handoff_required:{user_id}"
        self.redis.client.delete(handoff_flag)
        print(f"[HANDOFF] Cleared handoff_required flag for user {user_id}")
    
    def is_handoff_pending(self, user_id: str) -> bool:
        """Check if handoff is currently pending for user."""
        handoff_flag = f"handoff_required:{user_id}"
        return bool(self.redis.client.get(handoff_flag))


# Singleton instance
handoff_detector = HandoffDetector()
