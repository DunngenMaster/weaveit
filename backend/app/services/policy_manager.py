"""
Reward-Weighted Policy ZSET (Sprint 15.4)

Instant learning: newly learned patterns affect next response immediately.
No waiting for vector retrieval - Redis ZSET provides sorted, scored patterns.
"""

from typing import List, Dict, Any, Tuple
from app.services.redis_client import redis_client


class PolicyManager:
    """
    Manages reward-weighted policy patterns in Redis ZSET.
    
    Key: policy:{user_id}:{domain}
    Type: Sorted Set (ZSET)
    Member: pattern text
    Score: reward * critic_score
    """
    
    def __init__(self):
        self.client = redis_client.client
        self.ttl_seconds = 90 * 24 * 60 * 60  # 90 days
    
    def add_pattern(
        self,
        user_id: str,
        domain: str,
        pattern: str,
        reward: float,
        critic_score: float
    ):
        """
        Add learned pattern to policy ZSET.
        
        Called by Sprint 14 Promotion Worker when writing SkillMemory.
        
        Args:
            user_id: User identifier
            domain: Domain/category (resume, coding, etc)
            pattern: Learned behavior pattern
            reward: Reward score (0.0-1.0)
            critic_score: Critic quality score (0.0-1.0)
        """
        policy_key = f"policy:{user_id}:{domain}"
        
        # Compute final score
        score = reward * critic_score
        
        # Add to sorted set (higher score = better pattern)
        self.client.zadd(policy_key, {pattern: score})
        
        # Set TTL
        self.client.expire(policy_key, self.ttl_seconds)
        
        print(f"[POLICY] Added pattern (score={score:.2f}): {pattern[:60]}...")
    
    def get_top_patterns(
        self,
        user_id: str,
        domain: str,
        limit: int = 3
    ) -> List[Tuple[str, float]]:
        """
        Get top-scoring patterns for user/domain.
        
        Used during context generation to inject learned behaviors.
        
        Args:
            user_id: User identifier
            domain: Domain/category
            limit: Maximum number of patterns to return
            
        Returns:
            List of (pattern, score) tuples, highest score first
        """
        policy_key = f"policy:{user_id}:{domain}"
        
        # Get top N patterns with scores (REV = descending order)
        # ZRANGE policy:{user_id}:{domain} 0 2 REV WITHSCORES
        results = self.client.zrange(
            policy_key,
            0,
            limit - 1,
            desc=True,  # Descending order (highest scores first)
            withscores=True
        )
        
        if not results:
            return []
        
        # Convert bytes to strings
        patterns = []
        for item, score in results:
            pattern = item.decode('utf-8') if isinstance(item, bytes) else item
            patterns.append((pattern, float(score)))
        
        return patterns
    
    def remove_pattern(self, user_id: str, domain: str, pattern: str):
        """
        Remove a pattern from policy.
        
        Args:
            user_id: User identifier
            domain: Domain/category
            pattern: Pattern to remove
        """
        policy_key = f"policy:{user_id}:{domain}"
        self.client.zrem(policy_key, pattern)
    
    def get_all_domains(self, user_id: str) -> List[str]:
        """
        Get all domains that have policies for this user.
        
        Returns:
            List of domain names
        """
        pattern = f"policy:{user_id}:*"
        
        try:
            cursor = 0
            domains = set()
            while True:
                cursor, keys = self.client.scan(cursor, match=pattern, count=100)
                for key in keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    # Extract domain from key: policy:{user_id}:{domain}
                    parts = key_str.split(':')
                    if len(parts) >= 3:
                        domains.add(parts[2])
                if cursor == 0:
                    break
            
            return list(domains)
        except Exception as e:
            print(f"[POLICY] Error getting domains: {e}")
            return []
    
    def format_patterns_for_context(
        self,
        user_id: str,
        domain: str,
        limit: int = 3
    ) -> str:
        """
        Format top patterns as context string for LLM prompt.
        
        Args:
            user_id: User identifier
            domain: Domain/category
            limit: Maximum patterns to include
            
        Returns:
            Formatted string ready to inject into prompt
        """
        patterns = self.get_top_patterns(user_id, domain, limit)
        
        if not patterns:
            return ""
        
        lines = ["LEARNED SUCCESSFUL PATTERNS (apply these):"]
        for pattern, score in patterns:
            lines.append(f"- [{score:.2f}] {pattern}")
        
        return "\n".join(lines)
    
    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get policy statistics for user.
        
        Returns:
            Dict with pattern counts by domain
        """
        domains = self.get_all_domains(user_id)
        
        stats = {
            "total_domains": len(domains),
            "patterns_by_domain": {}
        }
        
        for domain in domains:
            policy_key = f"policy:{user_id}:{domain}"
            count = self.client.zcard(policy_key)
            stats["patterns_by_domain"][domain] = count
        
        return stats


# Global instance
policy_manager = PolicyManager()
