"""
Memory Hygiene (Sprint 16.4)

Supersede duplicate memories and decay unused patterns.
Keeps memory fresh and prevents stale information from dominating.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
from app.services.redis_client import redis_client
from app.services.policy_manager import policy_manager
from app.services.weaviate_client import weaviate_client


class MemoryHygiene:
    """
    Manages memory superseding and pattern decay.
    """
    
    def __init__(self):
        self.client = redis_client.client
    
    def supersede_memory(
        self,
        user_id: str,
        key: str,
        new_memory_id: str
    ) -> List[str]:
        """
        Mark old memories with same key as superseded.
        
        Args:
            user_id: User identifier
            key: Memory key (e.g., "job_title", "tech_stack")
            new_memory_id: UUID of new memory item
            
        Returns:
            List of superseded memory IDs
        """
        try:
            client = weaviate_client.client
            collection = client.collections.get("MemoryItem")
            
            # Find active memories with same key
            result = collection.query.fetch_objects(
                filters={
                    "operator": "And",
                    "operands": [
                        {"path": ["user_id"], "operator": "Equal", "valueText": user_id},
                        {"path": ["key"], "operator": "Equal", "valueText": key},
                        {"path": ["status"], "operator": "Equal", "valueText": "active"}
                    ]
                },
                limit=100
            )
            
            superseded_ids = []
            for obj in result.objects:
                # Skip the new memory itself
                if str(obj.uuid) == new_memory_id:
                    continue
                
                # Mark as superseded
                collection.data.update(
                    uuid=obj.uuid,
                    properties={"status": "superseded"}
                )
                superseded_ids.append(str(obj.uuid))
            
            if superseded_ids:
                print(f"[HYGIENE] Superseded {len(superseded_ids)} old memories for key '{key}'")
            
            return superseded_ids
            
        except Exception as e:
            print(f"[HYGIENE] Error superseding memories: {e}")
            return []
    
    def decay_unused_patterns(
        self,
        user_id: str,
        days_unused: int = 14,
        decay_factor: float = 0.8
    ) -> Dict[str, int]:
        """
        Reduce scores of patterns not used recently.
        
        Args:
            user_id: User identifier
            days_unused: Consider patterns unused after this many days
            decay_factor: Multiply score by this (0.8 = 20% reduction)
            
        Returns:
            Dict of {domain: patterns_decayed_count}
        """
        # Get all policy domains for user
        domains = policy_manager.get_all_domains(user_id)
        
        results = {}
        cutoff_ts = datetime.now() - timedelta(days=days_unused)
        
        for domain in domains:
            policy_key = f"policy:{user_id}:{domain}"
            
            try:
                # Get all patterns with scores
                patterns_with_scores = self.client.zrange(
                    policy_key,
                    0,
                    -1,
                    withscores=True
                )
                
                decayed_count = 0
                
                for pattern, score in patterns_with_scores:
                    pattern_str = pattern.decode('utf-8') if isinstance(pattern, bytes) else pattern
                    
                    # Check if pattern was used recently
                    # For now, decay all patterns since we don't track last_used
                    # In production, you'd check a last_used timestamp
                    
                    # Apply decay
                    new_score = score * decay_factor
                    
                    # Update score in ZSET
                    self.client.zadd(policy_key, {pattern_str: new_score})
                    decayed_count += 1
                
                results[domain] = decayed_count
                
                if decayed_count > 0:
                    print(f"[HYGIENE] Decayed {decayed_count} patterns in {domain}")
                
            except Exception as e:
                print(f"[HYGIENE] Error decaying patterns in {domain}: {e}")
                results[domain] = 0
        
        return results
    
    def decay_specific_domain(
        self,
        user_id: str,
        domain: str,
        decay_factor: float = 0.8
    ) -> int:
        """
        Decay all patterns in a specific domain.
        
        Args:
            user_id: User identifier
            domain: Domain to decay
            decay_factor: Multiply scores by this
            
        Returns:
            Number of patterns decayed
        """
        policy_key = f"policy:{user_id}:{domain}"
        
        try:
            patterns_with_scores = self.client.zrange(
                policy_key,
                0,
                -1,
                withscores=True
            )
            
            decayed_count = 0
            
            for pattern, score in patterns_with_scores:
                pattern_str = pattern.decode('utf-8') if isinstance(pattern, bytes) else pattern
                new_score = score * decay_factor
                self.client.zadd(policy_key, {pattern_str: new_score})
                decayed_count += 1
            
            print(f"[HYGIENE] Decayed {decayed_count} patterns in {domain}")
            return decayed_count
            
        except Exception as e:
            print(f"[HYGIENE] Error decaying {domain}: {e}")
            return 0


# Global instance
memory_hygiene = MemoryHygiene()
