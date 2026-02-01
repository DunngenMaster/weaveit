"""
Critic: Quality scoring for AI responses.

Judges response quality and compliance for later promotion decisions.
Only high-quality, compliant responses become learning material.
"""

import json
from typing import List, Literal
from pydantic import BaseModel, Field
from app.services.gemini_client import gemini_client
from dashboard.publisher import dashboard


ViolationType = Literal["FABRICATION", "POLICY_BLOCKED", "NOT_SPECIFIC", "TOO_LONG", "MISALIGNED"]


class CriticResult(BaseModel):
    """Strict output schema for critic scoring."""
    critic_score: float = Field(ge=0.0, le=1.0, description="Quality score 0.0-1.0")
    violations: List[ViolationType] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


async def score_response(
    user_text: str,
    assistant_text: str,
    context: str = ""
) -> CriticResult:
    """
    Call Gemini to score the quality of an AI response.
    
    Args:
        user_text: The user's original request
        assistant_text: The AI's response to evaluate
        context: Optional context about the conversation
        
    Returns:
        CriticResult with score (0.0-1.0) and any violations
        
    Violations:
    - FABRICATION: Response contains made-up facts or false information
    - POLICY_BLOCKED: Response violates safety/ethical policies
    - NOT_SPECIFIC: Response is too vague or generic
    - TOO_LONG: Response is unnecessarily verbose
    - MISALIGNED: Response doesn't address the user's actual request
    
    Scoring guide:
    - 0.9-1.0: Excellent - specific, accurate, helpful
    - 0.7-0.9: Good - mostly helpful with minor issues
    - 0.5-0.7: Acceptable - meets basic requirements
    - 0.3-0.5: Poor - significant issues
    - 0.0-0.3: Bad - major violations or unhelpful
    """
    
    system_prompt = """You are a quality critic for AI assistant responses.
Evaluate the AI's response for quality and compliance.

Check for these VIOLATIONS:
- FABRICATION: Contains made-up facts, false information, or invented credentials
- POLICY_BLOCKED: Violates safety/ethical policies (illegal, harmful, unethical)
- NOT_SPECIFIC: Too vague, generic, or lacks actionable detail
- TOO_LONG: Unnecessarily verbose or repetitive
- MISALIGNED: Doesn't address the user's actual request

SCORING (0.0 to 1.0):
- 0.9-1.0: Excellent - specific, accurate, directly helpful, concise
- 0.7-0.9: Good - helpful with minor issues
- 0.5-0.7: Acceptable - meets basic requirements
- 0.3-0.5: Poor - significant quality issues
- 0.0-0.3: Bad - major violations or unhelpful

Return ONLY valid JSON with this exact structure:
{
  "critic_score": 0.85,
  "violations": ["NOT_SPECIFIC"],
  "reasons": ["Response could be more specific about X"]
}

If no violations: violations=[], reasons=[]
"""

    user_prompt = f"""USER REQUEST:
{user_text}

AI RESPONSE:
{assistant_text}

{f'CONTEXT: {context}' if context else ''}

Evaluate the AI response quality and compliance."""
    
    try:
        response = await gemini_client.generate_content_async(
            prompt=user_prompt,
            system_instruction=system_prompt,
            temperature=0.2,  # Low temperature for consistent scoring
            max_tokens=200
        )
        
        # Parse JSON response
        result_json = json.loads(response.strip())
        result = CriticResult(**result_json)
        
        # Publish to live dashboard
        dashboard.publish_sync("judge_evaluation", {
            "score": result.critic_score,
            "violations": result.violations,
            "reasons": result.reasons,
            "criteria": "quality_compliance"
        })
        
        return result
        
    except json.JSONDecodeError as e:
        # Fallback: if JSON parse fails, give neutral score
        print(f"[CRITIC] JSON parse error: {e}, using neutral score")
        return CriticResult(
            critic_score=0.5,
            violations=[],
            reasons=["parse_error"]
        )
    except Exception as e:
        # Fallback: if API fails, give neutral score
        print(f"[CRITIC] Error: {e}, using neutral score")
        return CriticResult(
            critic_score=0.5,
            violations=[],
            reasons=["api_error"]
        )


# Singleton instance
critic = score_response
