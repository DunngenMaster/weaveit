"""
Story 18.2: CSA Builder Agent (Gemini JSON-only)

Uses Gemini to build a Conversation Snapshot Artifact from:
- Redis bundle (working memory)
- Last 5 session summaries
- Best successful attempt from attempt thread
- Top 3 policy patterns
- Top 5 relevant memories from Weaviate
"""

import json
import time
from uuid import uuid4
from typing import Dict, Any, Optional, List
from app.services.gemini_client import gemini_client
from app.services.redis_client import redis_client
from app.services.policy_manager import policy_manager
from app.services.skill_memory_retriever import skill_memory_retriever
from app.services.attempt_thread import attempt_thread_manager
from app.schemas.csa import ConversationSnapshotArtifact


CSA_BUILDER_PROMPT = """You are a conversation snapshot builder. Your task is to create a comprehensive, structured summary of a user's conversation session.

You will receive:
1. Working memory (recent events, context)
2. Session summaries (high-level progress)
3. Best successful attempt (what worked)
4. Learned patterns (what the system knows works for this user)
5. Relevant memories (similar past experiences)

Your output MUST be valid JSON matching this exact schema:

{
  "title": "Brief title (max 100 chars)",
  "user_intent": "What the user was trying to accomplish",
  "what_we_did": ["Action 1", "Action 2", ...],
  "what_worked": ["Success 1", "Success 2", ...],
  "what_failed": ["High-level failure description (NO raw failed content)", ...],
  "constraints": ["Constraint 1 (time/budget/requirements)", ...],
  "preferences": ["Preference 1 (style/format)", ...],
  "key_entities": {
    "companies": ["Company A", "Company B"],
    "role": "Target role or topic",
    "technologies": ["Tech A", "Tech B"],
    "documents": ["doc1.pdf", "doc2.txt"]
  },
  "artifacts": [
    {
      "type": "resume|code|document|analysis",
      "name": "artifact_name",
      "description": "What this artifact is",
      "quality_score": 0.0-1.0
    }
  ],
  "next_steps": ["Next action 1", "Next action 2", ...],
  "instructions_for_next_model": ["Instruction 1", "Instruction 2", ...]
}

CRITICAL RULES:
1. DO NOT include raw conversation transcripts
2. DO NOT include disallowed or sensitive content
3. what_failed should be HIGH-LEVEL only (e.g., "First resume draft was too verbose")
4. Focus on ACTIONABLE insights for the next model
5. key_entities should extract concrete names, not generic descriptions
6. instructions_for_next_model should capture user's working style and preferences
7. Output ONLY valid JSON, no markdown code blocks, no explanations

Input data:
---
{input_data}
---

Generate the CSA JSON now:"""


class CSABuilder:
    """Builds Conversation Snapshot Artifacts using Gemini."""
    
    def __init__(self):
        self.gemini = gemini_client
        self.redis = redis_client
    
    async def build_csa(
        self,
        user_id: str,
        source_provider: str,
        source_session_id: str,
        domain: str = "unknown"
    ) -> ConversationSnapshotArtifact:
        """
        Build a CSA from all available sources.
        
        Args:
            user_id: User identifier
            source_provider: Provider where conversation originated
            source_session_id: Session identifier from source
            domain: Domain for policy patterns
            
        Returns:
            ConversationSnapshotArtifact with complete snapshot
        """
        # Gather input data from all sources
        input_data = await self._gather_input_data(user_id, domain)
        
        # Build prompt with all context
        prompt = CSA_BUILDER_PROMPT.format(input_data=json.dumps(input_data, indent=2))
        
        # Call Gemini to generate CSA JSON
        try:
            response = await self.gemini.generate_json(
                prompt=prompt,
                timeout=10.0
            )
            
            # Debug to file since console logs aren't showing
            with open("csa_debug.log", "a") as f:
                f.write(f"\n[CSA_BUILDER] Gemini returned type: {type(response)}\n")
                f.write(f"[CSA_BUILDER] Gemini response: {str(response)[:500]}\n")
            
            # Parse response to CSA (response is already a dict from generate_json)
            csa_data = response
            
            with open("csa_debug.log", "a") as f:
                f.write(f"[CSA_BUILDER] CSA data is dict: {isinstance(csa_data, dict)}\n")
                f.write(f"[CSA_BUILDER] CSA data keys: {list(csa_data.keys()) if isinstance(csa_data, dict) else 'NOT A DICT'}\n")
            
            # Add required metadata fields
            csa = ConversationSnapshotArtifact(
                csa_id=str(uuid4()),
                schema_version=1,
                user_id=user_id,
                created_ts_ms=int(time.time() * 1000),
                source_provider=source_provider,
                source_session_id=source_session_id,
                **csa_data
            )
            
            print(f"[CSA_BUILDER] Successfully built CSA from Gemini: {csa.csa_id}")
            return csa
            
        except Exception as e:
            # Fallback: create minimal CSA on error (e.g., Gemini API key expired, timeout, etc.)
            with open("csa_debug.log", "a") as f:
                f.write(f"\n[CSA_BUILDER] ERROR: {type(e).__name__}: {str(e)[:500]}\n")
                import traceback
                traceback.print_exc(file=f)
            print(f"[CSA_BUILDER] Gemini failed ({type(e).__name__}: {str(e)[:200]}), using minimal CSA")
            import traceback
            traceback.print_exc()
            return self._create_minimal_csa(user_id, source_provider, source_session_id)
    
    async def _gather_input_data(self, user_id: str, domain: str) -> Dict[str, Any]:
        """Gather all input data for CSA builder."""
        
        # 1. Redis bundle (working memory)
        bundle_key = f"bundle:{user_id}"
        bundle_data = self.redis.client.get(bundle_key)
        bundle = json.loads(bundle_data) if bundle_data else {}
        
        # 2. Last 5 session summaries (if available)
        summaries_key = f"summaries:{user_id}"
        summaries_data = self.redis.client.lrange(summaries_key, 0, 4)
        summaries = [json.loads(s) for s in summaries_data] if summaries_data else []
        
        # 3. Best successful attempt from attempt thread
        best_attempt = None
        try:
            # Get all attempt threads for user
            thread_pattern = f"thread:*:{user_id}"
            thread_keys = self.redis.client.keys(thread_pattern)
            
            # Find best attempt across all threads
            for thread_key in thread_keys[:10]:  # Limit to recent 10 threads
                thread_data = self.redis.client.hgetall(thread_key)
                if thread_data and thread_data.get('status') == 'resolved':
                    best_reward = float(thread_data.get('best_reward', 0))
                    if best_reward >= 0.6:  # Minimum success threshold
                        best_attempt = {
                            'fingerprint': thread_data.get('fingerprint'),
                            'reward': best_reward,
                            'outcome': thread_data.get('outcome'),
                            'attempt_count': thread_data.get('attempt_count')
                        }
                        break
        except Exception as e:
            print(f"[CSA_BUILDER] Error fetching best attempt: {e}")
        
        # 4. Top 3 policy patterns
        patterns = []
        try:
            policy_key = f"policy:{user_id}:{domain}"
            pattern_data = self.redis.client.zrevrange(policy_key, 0, 2, withscores=True)
            patterns = [
                {"pattern": p[0].decode() if isinstance(p[0], bytes) else p[0], "score": p[1]}
                for p in pattern_data
            ] if pattern_data else []
        except Exception as e:
            print(f"[CSA_BUILDER] Error fetching patterns: {e}")
        
        # 5. Top 5 relevant memories from Weaviate (optional)
        memories = []
        try:
            # Use user's recent context to find relevant memories
            query_text = bundle.get('active_goal', '') or bundle.get('recent_topics', [''])[0]
            if query_text:
                memory_results = await skill_memory_retriever.retrieve(
                    user_id=user_id,
                    query=query_text,
                    limit=5,
                    min_quality=0.5
                )
                memories = [
                    {
                        'pattern': m.get('pattern', ''),
                        'quality': m.get('quality', 0),
                        'domain': m.get('domain', '')
                    }
                    for m in memory_results
                ]
        except Exception as e:
            print(f"[CSA_BUILDER] Error fetching memories: {e}")
        
        # Compile all input data
        return {
            "working_memory": bundle,
            "session_summaries": summaries,
            "best_attempt": best_attempt,
            "learned_patterns": patterns,
            "relevant_memories": memories,
            "user_id": user_id,
            "domain": domain
        }
    
    def _create_minimal_csa(
        self,
        user_id: str,
        source_provider: str,
        source_session_id: str
    ) -> ConversationSnapshotArtifact:
        """Create minimal CSA when builder fails."""
        return ConversationSnapshotArtifact(
            csa_id=str(uuid4()),
            schema_version=1,
            user_id=user_id,
            created_ts_ms=int(time.time() * 1000),
            source_provider=source_provider,
            source_session_id=source_session_id,
            title="Conversation Snapshot (Minimal)",
            user_intent="Unable to determine user intent",
            what_we_did=["Previous conversation occurred"],
            what_worked=[],
            what_failed=["CSA generation encountered an error"],
            constraints=[],
            preferences=[],
            key_entities={},
            artifacts=[],
            next_steps=["Continue conversation with new context"],
            instructions_for_next_model=["User is continuing from a previous session"]
        )


# Singleton instance
csa_builder = CSABuilder()
