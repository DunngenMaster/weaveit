"""
Sprint 17.6: SkillMemory Retrieval with Quality Gating

Hybrid search + quality reranking ensures only high-quality patterns
are injected into context, fixing the "20 attempts, only 20th is good" problem.
"""

from typing import List, Dict, Any
from datetime import datetime, timezone
from app.services.weaviate_client import weaviate_client
import weaviate.classes as wvc


class SkillMemoryRetriever:
    """
    Retrieve learned patterns from SkillMemory with quality gating.
    
    Sprint 17.6 Rules:
    - Hybrid search (alpha=0.6) for better precision
    - Max distance threshold to reject junk matches
    - Client-side reranking by quality score (reward * critic_score)
    - Quality threshold: only inject patterns with quality >= 0.5
    """
    
    def __init__(self, min_quality: float = 0.5, max_distance: float = 0.75):
        self.client = weaviate_client.client
        self.min_quality = min_quality
        self.max_distance = max_distance
    
    def retrieve_patterns(
        self,
        user_id: str,
        domain: str,
        query_text: str = "",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve top skill patterns with quality gating.
        
        Args:
            user_id: User identifier
            domain: Domain to filter (e.g., "resume", "coding", "interview")
            query_text: Query for hybrid search (optional)
            limit: Maximum patterns to return
            
        Returns:
            List of skill patterns sorted by quality score
        """
        try:
            collection = self.client.collections.get("SkillMemory")
            
            # Build filters: user_id + domain + active status
            filters = (
                wvc.query.Filter.by_property("user_id").equal(user_id) &
                wvc.query.Filter.by_property("domain").equal(domain) &
                wvc.query.Filter.by_property("status").equal("active")
            )
            
            # Build keyword query from domain + tags
            if not query_text:
                query_text = f"{domain} pattern instruction"
            
            # Hybrid search: alpha=0.6 (favor vector similarity)
            result = collection.query.hybrid(
                query=query_text,
                alpha=0.6,
                limit=limit * 2,  # Retrieve more for quality filtering
                filters=filters,
                return_metadata=wvc.query.MetadataQuery(distance=True)
            )
            
            # Extract patterns with quality gating
            patterns = []
            for obj in result.objects:
                # Check max distance threshold
                if obj.metadata.distance and obj.metadata.distance > self.max_distance:
                    continue
                
                props = obj.properties
                quality = props.get('quality', 0.0)
                
                # Quality gate: only accept high-quality patterns
                if quality < self.min_quality:
                    continue
                
                patterns.append({
                    'pattern': props.get('pattern', ''),
                    'context': props.get('context', ''),
                    'domain': props.get('domain', ''),
                    'tags': props.get('tags', []),
                    'reward': props.get('reward', 0.0),
                    'critic_score': props.get('critic_score', 0.0),
                    'quality': quality,
                    'distance': obj.metadata.distance if obj.metadata.distance else 0.0,
                    'source_attempt_id': props.get('source_attempt_id', ''),
                    'created_at': props.get('created_at', None)
                })
            
            # Rerank by quality score (descending)
            patterns.sort(key=lambda p: p['quality'], reverse=True)
            
            # Return top N after quality filtering
            return patterns[:limit]
            
        except Exception as e:
            print(f"[SKILL_MEMORY] Error retrieving patterns: {e}")
            return []
    
    def retrieve_multi_domain(
        self,
        user_id: str,
        domains: List[str],
        query_text: str = "",
        limit_per_domain: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve patterns across multiple domains.
        
        Args:
            user_id: User identifier
            domains: List of domains to query
            query_text: Query for hybrid search
            limit_per_domain: Max patterns per domain
            
        Returns:
            Dict mapping domain -> patterns
        """
        results = {}
        
        for domain in domains:
            patterns = self.retrieve_patterns(
                user_id=user_id,
                domain=domain,
                query_text=query_text,
                limit=limit_per_domain
            )
            results[domain] = patterns
        
        return results
    
    def store_pattern(
        self,
        user_id: str,
        domain: str,
        pattern: str,
        context: str,
        tags: List[str],
        reward: float,
        critic_score: float,
        source_attempt_id: str
    ) -> bool:
        """
        Store a new skill pattern with quality score.
        
        Args:
            user_id: User identifier
            domain: Domain (e.g., "resume", "coding")
            pattern: The learned pattern/instruction
            context: When to apply this pattern
            tags: Relevant tags
            reward: Reward score (0.0 - 1.0)
            critic_score: Critic score (0.0 - 1.0)
            source_attempt_id: Attempt that generated this pattern
            
        Returns:
            True if stored successfully
        """
        try:
            quality = reward * critic_score
            
            # Quality threshold: don't store garbage patterns
            if quality < 0.3:
                print(f"[SKILL_MEMORY] Rejecting low-quality pattern (quality={quality:.2f})")
                return False
            
            collection = self.client.collections.get("SkillMemory")
            
            collection.data.insert({
                'user_id': user_id,
                'domain': domain,
                'pattern': pattern,
                'context': context,
                'tags': tags,
                'reward': reward,
                'critic_score': critic_score,
                'quality': quality,
                'source_attempt_id': source_attempt_id,
                'status': 'active',
                'created_at': datetime.now(timezone.utc)
            })
            
            print(f"[SKILL_MEMORY] Stored pattern for domain={domain}, quality={quality:.2f}")
            return True
            
        except Exception as e:
            print(f"[SKILL_MEMORY] Error storing pattern: {e}")
            return False
    
    def format_patterns_for_injection(self, patterns: List[Dict[str, Any]]) -> str:
        """
        Format skill patterns for injection into LLM context.
        
        Args:
            patterns: List of pattern dicts
            
        Returns:
            Formatted string ready for context injection
        """
        if not patterns:
            return ""
        
        lines = ["LEARNED_PATTERNS:", ""]
        
        for i, p in enumerate(patterns, 1):
            quality = p.get('quality', 0.0)
            lines.append(f"{i}. [{p.get('domain', 'unknown').upper()}] (quality: {quality:.2f})")
            lines.append(f"   Pattern: {p.get('pattern', '')}")
            if p.get('context'):
                lines.append(f"   Context: {p.get('context', '')}")
            lines.append("")
        
        return "\n".join(lines)


# Global instance
skill_memory_retriever = SkillMemoryRetriever(min_quality=0.5, max_distance=0.75)
