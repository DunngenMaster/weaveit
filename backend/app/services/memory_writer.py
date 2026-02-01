from typing import Dict, List, Any
from app.services.gemini_client import gemini_client
from dashboard.publisher import dashboard


MEMORY_EXTRACTION_PROMPT = """You are a memory extraction assistant. Analyze the conversation and extract structured information.

Input:
- User message: {user_message}
- Assistant response: {assistant_message}
- Current goal/task: {session_goal}
- Recent summaries: {recent_summaries}

Extract the following information in JSON format:

{{
  "session_summary": "3-6 bullet points summarizing this exchange",
  "next_steps": ["action 1", "action 2"],
  "candidates": [
    {{
      "kind": "GOAL|PREFERENCE|CONSTRAINT|DECISION|ARTIFACT|PROFILE",
      "key": "unique_identifier",
      "text": "descriptive text",
      "tags": ["tag1", "tag2"],
      "confidence": 0.0-1.0,
      "ttl_days": 30,
      "dedupe_key": "unique_hash_for_deduplication"
    }}
  ],
  "safety": {{
    "store_allowed": true,
    "reason": "explanation"
  }}
}}

Rules:
- Only extract clear, confident information
- Confidence < 0.75 means uncertain
- Store_allowed=false if sensitive/private data detected
- Dedupe_key should be hash of (kind+key+text)
- Return ONLY valid JSON, no markdown
"""


class MemoryWriter:
    
    def extract_memories(
        self,
        user_message: str,
        assistant_message: str,
        session_goal: str = "",
        recent_summaries: List[str] = None
    ) -> Dict[str, Any]:
        
        if recent_summaries is None:
            recent_summaries = []
        
        summaries_text = "\n".join(recent_summaries[-5:]) if recent_summaries else "None"
        
        prompt = MEMORY_EXTRACTION_PROMPT.format(
            user_message=user_message,
            assistant_message=assistant_message,
            session_goal=session_goal or "Not specified",
            recent_summaries=summaries_text
        )
        
        result = gemini_client.generate_json(prompt)
        
        if "session_summary" not in result:
            result["session_summary"] = ""
        if "next_steps" not in result:
            result["next_steps"] = []
        if "candidates" not in result:
            result["candidates"] = []
        if "safety" not in result:
            result["safety"] = {"store_allowed": True, "reason": "No issues detected"}
        
        # Publish memory candidates to dashboard
        for candidate in result.get("candidates", []):
            dashboard.publish_sync("memory_write", {
                "kind": candidate.get("kind", "UNKNOWN"),
                "key": candidate.get("key", ""),
                "confidence": candidate.get("confidence", 0.0),
                "text_preview": candidate.get("text", "")[:50]
            })
        
        return result


memory_writer = MemoryWriter()
