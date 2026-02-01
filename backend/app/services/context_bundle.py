"""
Redis Context Bundle (Sprint 15.2)

Always-ready context snapshot for offline RAG.
Provides meaningful context even when Weaviate is slow/down.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.services.redis_client import redis_client


class ContextBundleManager:
    """
    Manages context bundles stored in Redis for fast, offline-capable RAG.
    
    Key: bundle:{user_id}
    TTL: 30 days
    """
    
    def __init__(self):
        self.client = redis_client.client
        self.ttl_seconds = 30 * 24 * 60 * 60  # 30 days
    
    def get_bundle(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get context bundle for user.
        
        Returns:
            Bundle dict with: active_goal, active_task, last_5_session_summaries,
            top_skill_patterns, last_context_by_provider, updated_ts
        """
        bundle_key = f"bundle:{user_id}"
        data = self.client.hgetall(bundle_key)
        
        if not data:
            return None
        
        # Convert bytes and parse JSON fields
        bundle = {}
        for k, v in data.items():
            key = k.decode('utf-8') if isinstance(k, bytes) else k
            value = v.decode('utf-8') if isinstance(v, bytes) else v
            
            # Parse JSON fields
            if key in ['last_5_session_summaries', 'top_skill_patterns', 'last_context_by_provider']:
                try:
                    bundle[key] = json.loads(value)
                except:
                    bundle[key] = value
            else:
                bundle[key] = value
        
        return bundle
    
    def update_goal(self, user_id: str, goal: str):
        """Update active goal in bundle"""
        bundle_key = f"bundle:{user_id}"
        self.client.hset(bundle_key, "active_goal", goal)
        self.client.hset(bundle_key, "updated_ts", datetime.now().isoformat())
        self.client.expire(bundle_key, self.ttl_seconds)
    
    def update_task(self, user_id: str, task: str):
        """Update active task in bundle"""
        bundle_key = f"bundle:{user_id}"
        self.client.hset(bundle_key, "active_task", task)
        self.client.hset(bundle_key, "updated_ts", datetime.now().isoformat())
        self.client.expire(bundle_key, self.ttl_seconds)
    
    def add_session_summary(self, user_id: str, summary: str):
        """
        Add session summary to bundle (keep last 5).
        
        Args:
            user_id: User identifier
            summary: Session summary text
        """
        bundle_key = f"bundle:{user_id}"
        
        # Get current summaries
        current = self.client.hget(bundle_key, "last_5_session_summaries")
        if current:
            summaries = json.loads(current) if isinstance(current, (str, bytes)) else []
            if isinstance(current, bytes):
                summaries = json.loads(current.decode('utf-8'))
        else:
            summaries = []
        
        # Add new summary and keep last 5
        summaries.append(summary)
        summaries = summaries[-5:]
        
        # Update bundle
        self.client.hset(bundle_key, "last_5_session_summaries", json.dumps(summaries))
        self.client.hset(bundle_key, "updated_ts", datetime.now().isoformat())
        self.client.expire(bundle_key, self.ttl_seconds)
    
    def update_skill_patterns(self, user_id: str, patterns: List[Dict[str, Any]]):
        """
        Update top skill patterns in bundle.
        
        Called when new SkillMemory is promoted.
        
        Args:
            user_id: User identifier
            patterns: List of {pattern, tags, reward, critic_score}
        """
        bundle_key = f"bundle:{user_id}"
        
        # Keep top 10 patterns by score
        sorted_patterns = sorted(
            patterns,
            key=lambda p: p.get('reward', 0) * p.get('critic_score', 0),
            reverse=True
        )[:10]
        
        self.client.hset(bundle_key, "top_skill_patterns", json.dumps(sorted_patterns))
        self.client.hset(bundle_key, "updated_ts", datetime.now().isoformat())
        self.client.expire(bundle_key, self.ttl_seconds)
    
    def update_last_context(self, user_id: str, provider: str, context: str):
        """
        Update last generated context by provider.
        
        Args:
            user_id: User identifier
            provider: Provider name (chatgpt, claude, etc)
            context: Generated context text
        """
        bundle_key = f"bundle:{user_id}"
        
        # Get current context map
        current = self.client.hget(bundle_key, "last_context_by_provider")
        if current:
            context_map = json.loads(current) if isinstance(current, (str, bytes)) else {}
            if isinstance(current, bytes):
                context_map = json.loads(current.decode('utf-8'))
        else:
            context_map = {}
        
        # Update for this provider
        context_map[provider] = {
            "context": context,
            "ts": datetime.now().isoformat()
        }
        
        self.client.hset(bundle_key, "last_context_by_provider", json.dumps(context_map))
        self.client.hset(bundle_key, "updated_ts", datetime.now().isoformat())
        self.client.expire(bundle_key, self.ttl_seconds)
    
    def build_minimal_context(self, user_id: str) -> str:
        """
        Build minimal safe context from bundle (for graceful degradation).
        
        This always succeeds even if Weaviate is down.
        
        Returns:
            Context string ready to inject into LLM prompt
        """
        bundle = self.get_bundle(user_id)
        
        if not bundle:
            return "No context available. Assist the user to the best of your ability."
        
        parts = []
        
        # Active goal
        if bundle.get('active_goal'):
            parts.append(f"USER'S CURRENT GOAL:\n{bundle['active_goal']}")
        
        # Active task
        if bundle.get('active_task'):
            parts.append(f"ACTIVE TASK:\n{bundle['active_task']}")
        
        # Recent summaries
        summaries = bundle.get('last_5_session_summaries', [])
        if summaries:
            parts.append("RECENT SESSION CONTEXT:\n" + "\n".join([f"- {s}" for s in summaries]))
        
        # Top skill patterns
        patterns = bundle.get('top_skill_patterns', [])
        if patterns:
            pattern_texts = [p.get('pattern', '') for p in patterns[:3]]
            parts.append("LEARNED BEHAVIORS:\n" + "\n".join([f"- {p}" for p in pattern_texts if p]))
        
        if not parts:
            return "No specific context available. Assist the user to the best of your ability."
        
        return "\n\n".join(parts)


# Global instance
context_bundle_manager = ContextBundleManager()
