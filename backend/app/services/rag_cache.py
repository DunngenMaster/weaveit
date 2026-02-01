"""
Redis RAG Cache (Sprint 15.3)

Accelerates Weaviate retrieval by caching vector search results.
10-minute TTL ensures fresh but fast context generation.
"""

import json
import hashlib
from typing import List, Dict, Any, Optional
from app.services.redis_client import redis_client


class RAGCache:
    """
    Caches Weaviate retrieval results in Redis.
    
    Key: rag_cache:{user_id}:{domain}:{provider}:{fingerprint}
    TTL: 10 minutes
    """
    
    def __init__(self):
        self.client = redis_client.client
        self.ttl_seconds = 10 * 60  # 10 minutes
    
    def _make_cache_key(
        self,
        user_id: str,
        domain: str,
        provider: str,
        fingerprint: str
    ) -> str:
        """
        Generate cache key for RAG results.
        
        Args:
            user_id: User identifier
            domain: Domain/category (resume, coding, etc)
            provider: Provider name (chatgpt, claude, etc)
            fingerprint: Message fingerprint
            
        Returns:
            Cache key string
        """
        # Shorten fingerprint for readability
        fp_short = fingerprint[:16] if fingerprint else "none"
        return f"rag_cache:{user_id}:{domain}:{provider}:{fp_short}"
    
    def get(
        self,
        user_id: str,
        domain: str,
        provider: str,
        fingerprint: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached RAG results.
        
        Returns:
            List of memory items or None if cache miss
        """
        cache_key = self._make_cache_key(user_id, domain, provider, fingerprint)
        
        cached_data = self.client.get(cache_key)
        if not cached_data:
            return None
        
        try:
            if isinstance(cached_data, bytes):
                cached_data = cached_data.decode('utf-8')
            return json.loads(cached_data)
        except Exception as e:
            print(f"[RAG_CACHE] Error parsing cache: {e}")
            return None
    
    def set(
        self,
        user_id: str,
        domain: str,
        provider: str,
        fingerprint: str,
        memories: List[Dict[str, Any]]
    ):
        """
        Cache RAG results.
        
        Args:
            user_id: User identifier
            domain: Domain/category
            provider: Provider name
            fingerprint: Message fingerprint
            memories: List of memory items to cache
        """
        cache_key = self._make_cache_key(user_id, domain, provider, fingerprint)
        
        try:
            cache_data = json.dumps(memories)
            self.client.setex(cache_key, self.ttl_seconds, cache_data)
            print(f"[RAG_CACHE] Cached {len(memories)} memories for {cache_key[:50]}...")
        except Exception as e:
            print(f"[RAG_CACHE] Error setting cache: {e}")
    
    def invalidate(self, user_id: str, domain: str = "*"):
        """
        Invalidate cache entries for user/domain.
        
        Called when new SkillMemory is promoted.
        
        Args:
            user_id: User identifier
            domain: Domain to invalidate (or * for all)
        """
        pattern = f"rag_cache:{user_id}:{domain}:*"
        
        try:
            # Find matching keys
            cursor = 0
            deleted_count = 0
            while True:
                cursor, keys = self.client.scan(cursor, match=pattern, count=100)
                if keys:
                    self.client.delete(*keys)
                    deleted_count += len(keys)
                if cursor == 0:
                    break
            
            if deleted_count > 0:
                print(f"[RAG_CACHE] Invalidated {deleted_count} cache entries for {user_id}")
        except Exception as e:
            print(f"[RAG_CACHE] Error invalidating cache: {e}")
    
    def get_stats(self, user_id: str) -> Dict[str, int]:
        """
        Get cache statistics for user.
        
        Returns:
            Dict with cache_entries count
        """
        pattern = f"rag_cache:{user_id}:*"
        
        try:
            cursor = 0
            count = 0
            while True:
                cursor, keys = self.client.scan(cursor, match=pattern, count=100)
                count += len(keys)
                if cursor == 0:
                    break
            
            return {"cache_entries": count}
        except Exception as e:
            print(f"[RAG_CACHE] Error getting stats: {e}")
            return {"cache_entries": 0}


# Global instance
rag_cache = RAGCache()
