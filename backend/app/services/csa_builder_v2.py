"""
CSA Builder Service - Sprint 18.2 (Clean Rewrite)

Builds Conversation Snapshot Artifacts using Gemini.
Simplified implementation with robust error handling.
"""

import json
import time
from uuid import uuid4
from typing import Dict, Any

from app.services.gemini_client import gemini_client
from app.services.redis_client import redis_client
from app.schemas.csa import ConversationSnapshotArtifact


CSA_BUILDER_PROMPT = """Create a Conversation Snapshot for AI handoff.

Return ONLY valid JSON matching this structure:
{{
  "title": "Brief session summary",
  "user_intent": "What user wants",
  "what_we_did": ["action 1"],
  "what_worked": ["success 1"],
  "what_failed": ["failure 1"],
  "constraints": [],
  "preferences": [],
  "key_entities": {{}},
  "artifacts": [],
  "next_steps": ["next action"],
  "instructions_for_next_model": ["guidance"]
}}

Session context: {context}

JSON:"""


class CSABuilder:
    """Builds CSAs from conversation context."""
    
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
        Build CSA from context.
        Falls back to minimal CSA on any error.
        """
        try:
            # Gather minimal context
            context = self._gather_context(user_id)
            
            # Build prompt
            prompt = CSA_BUILDER_PROMPT.format(context=json.dumps(context))
            
            # Call Gemini
            response = await self.gemini.generate_json(prompt=prompt, timeout=10.0)
            
            # Validate response is dict
            if not isinstance(response, dict):
                raise ValueError(f"Gemini returned {type(response)}, expected dict")
            
            # Create CSA
            csa = ConversationSnapshotArtifact(
                csa_id=str(uuid4()),
                schema_version=1,
                user_id=user_id,
                created_ts_ms=int(time.time() * 1000),
                source_provider=source_provider,
                source_session_id=source_session_id,
                **response
            )
            
            print(f"[CSA_BUILDER] Built CSA: {csa.csa_id}")
            return csa
            
        except Exception as e:
            print(f"[CSA_BUILDER] Error: {type(e).__name__}: {str(e)[:200]}")
            print(f"[CSA_BUILDER] Falling back to minimal CSA")
            return self._create_minimal_csa(user_id, source_provider, source_session_id)
    
    def _gather_context(self, user_id: str) -> Dict[str, Any]:
        """Gather basic context from Redis."""
        context = {"user_id": user_id}
        
        try:
            # Get bundle if exists
            bundle_key = f"bundle:{user_id}"
            bundle_data = self.redis.client.get(bundle_key)
            if bundle_data:
                context["bundle"] = json.loads(bundle_data)
        except Exception as e:
            print(f"[CSA_BUILDER] Could not load bundle: {e}")
        
        return context
    
    def _create_minimal_csa(
        self,
        user_id: str,
        source_provider: str,
        source_session_id: str
    ) -> ConversationSnapshotArtifact:
        """Create minimal fallback CSA."""
        return ConversationSnapshotArtifact(
            csa_id=str(uuid4()),
            schema_version=1,
            user_id=user_id,
            created_ts_ms=int(time.time() * 1000),
            source_provider=source_provider,
            source_session_id=source_session_id,
            title="Conversation Snapshot",
            user_intent="Continue previous work",
            what_we_did=["Had a conversation"],
            what_worked=[],
            what_failed=[],
            constraints=[],
            preferences=[],
            key_entities={},
            artifacts=[],
            next_steps=["Continue conversation"],
            instructions_for_next_model=["Continue from where we left off"]
        )


# Singleton instance
csa_builder = CSABuilder()
