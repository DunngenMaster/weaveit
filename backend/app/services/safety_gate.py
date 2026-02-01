"""
Safety Gate: Pre-storage classification to block disallowed requests.

Prevents harmful/unethical requests from entering long-term memory.
Only minimal counters are kept for blocked requests.
"""

import json
from typing import Literal
from pydantic import BaseModel, Field
from app.services.gemini_client import gemini_client


class SafetyResult(BaseModel):
    """Strict output schema for safety classification."""
    allowed: bool
    store_policy: Literal["STORE_NORMAL", "STORE_NOTHING"]
    category: str = Field(default="NONE")
    reason_short: str


async def classify_safety(user_text: str) -> SafetyResult:
    """
    Call Gemini to classify if user request is allowed.
    
    Args:
        user_text: The user's message text
        
    Returns:
        SafetyResult with allowed flag and storage policy
        
    Blocked categories include:
    - FABRICATION (fake resume, false credentials)
    - ILLEGAL (hacking, fraud, violence)
    - UNETHICAL (deception, manipulation)
    - HARMFUL (dangerous advice, self-harm)
    """
    
    system_prompt = """You are a safety classifier for an AI assistant.
Classify if the user's request should be allowed or blocked.

BLOCK these categories:
- FABRICATION: requests to create fake resumes, fabricate experience, lie about credentials
- ILLEGAL: hacking, fraud, violence, illegal activities
- UNETHICAL: deception, manipulation, scams
- HARMFUL: dangerous advice, self-harm, extremism

ALLOW everything else, including:
- Legitimate resume writing (real experience)
- Job search help
- Coding, learning, productivity
- General assistance

Return ONLY valid JSON with this exact structure:
{
  "allowed": true or false,
  "store_policy": "STORE_NORMAL" or "STORE_NOTHING",
  "category": "FABRICATION" or "ILLEGAL" or "UNETHICAL" or "HARMFUL" or "NONE",
  "reason_short": "brief reason (max 50 chars)"
}

If blocked: allowed=false, store_policy="STORE_NOTHING", category=one of the blocked types
If allowed: allowed=true, store_policy="STORE_NORMAL", category="NONE"
"""

    user_prompt = f"Classify this request:\n\n{user_text}"
    
    try:
        response = await gemini_client.generate_content_async(
            prompt=user_prompt,
            system_instruction=system_prompt,
            temperature=0.1,  # Low temperature for consistent classification
            max_tokens=150
        )
        
        # Parse JSON response
        result_json = json.loads(response.strip())
        return SafetyResult(**result_json)
        
    except json.JSONDecodeError as e:
        # Fallback: if JSON parse fails, allow by default (fail-open for user experience)
        print(f"[SAFETY_GATE] JSON parse error: {e}, allowing request")
        return SafetyResult(
            allowed=True,
            store_policy="STORE_NORMAL",
            category="NONE",
            reason_short="parse_error_fail_open"
        )
    except Exception as e:
        # Fallback: if API fails, allow by default
        print(f"[SAFETY_GATE] Error: {e}, allowing request")
        return SafetyResult(
            allowed=True,
            store_policy="STORE_NORMAL",
            category="NONE",
            reason_short="api_error_fail_open"
        )


# Singleton instance
safety_gate = classify_safety
