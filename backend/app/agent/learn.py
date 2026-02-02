import json
from app.agent.prompts import LEARNER_PROMPT
from app.services.llm_factory import get_chat_model
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class LearnOutput(BaseModel):
    policy_delta: dict = Field(default_factory=dict)
    prompt_delta: dict = Field(default_factory=dict)
    rationale: str = Field(min_length=1)
    
    @field_validator('policy_delta')
    @classmethod
    def validate_policy_delta(cls, v):
        """Validate policy_delta has correct types and ranges"""
        if not isinstance(v, dict):
            return {}
        
        validated = {}
        
        # Validate max_tabs: should be int between 1 and 20
        if 'max_tabs' in v:
            try:
                max_tabs = int(v['max_tabs'])
                if 1 <= max_tabs <= 20:
                    validated['max_tabs'] = max_tabs
            except (ValueError, TypeError):
                pass
        
        # Validate min_score: should be float between 0.0 and 1.0
        if 'min_score' in v:
            try:
                min_score = float(v['min_score'])
                if 0.0 <= min_score <= 1.0:
                    validated['min_score'] = min_score
            except (ValueError, TypeError):
                pass
        
        # Validate unique_domains: should be int 0 or 1
        if 'unique_domains' in v:
            try:
                unique_domains = int(v['unique_domains'])
                if unique_domains in [0, 1]:
                    validated['unique_domains'] = unique_domains
            except (ValueError, TypeError):
                pass
        
        return validated
    
    @field_validator('prompt_delta')
    @classmethod
    def validate_prompt_delta(cls, v):
        """Validate prompt_delta structure"""
        if not isinstance(v, dict):
            return {}
        
        validated = {}
        
        # search_focus should be a non-empty string
        if 'search_focus' in v and isinstance(v['search_focus'], str) and v['search_focus']:
            validated['search_focus'] = v['search_focus'][:200]  # Cap length
        
        # avoid_domains should be list of strings
        if 'avoid_domains' in v and isinstance(v['avoid_domains'], list):
            validated['avoid_domains'] = [d for d in v['avoid_domains'] if isinstance(d, str)][:10]
        
        # prefer_domains should be list of strings
        if 'prefer_domains' in v and isinstance(v['prefer_domains'], list):
            validated['prefer_domains'] = [d for d in v['prefer_domains'] if isinstance(d, str)][:10]
        
        return validated


def _generate_fallback_patch(feedback: dict) -> dict:
    """
    Generate a safe fallback patch when LLM fails.
    Uses simple heuristics based on feedback tags.
    """
    tags = feedback.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except:
            tags = []
    
    notes = (feedback.get("notes", "") or "").lower()
    
    policy_delta = {}
    prompt_delta = {}
    rationale = "Fallback patch: "
    
    # Simple tag-based rules
    if "too_many_results" in tags or "too_many_tabs" in tags:
        policy_delta["max_tabs"] = 5
        rationale += "Reduced tabs; "
    elif "too_few_results" in tags:
        policy_delta["max_tabs"] = 15
        rationale += "Increased tabs; "
    
    if "low_quality" in tags or "irrelevant" in tags:
        policy_delta["min_score"] = 0.75
        rationale += "Raised quality threshold; "
    
    # Domain preferences from notes
    if any(word in notes for word in ["no amazon", "avoid amazon", "not amazon"]):
        prompt_delta["avoid_domains"] = ["amazon.com"]
        rationale += "Avoiding marketplace sites; "
    
    if any(word in notes for word in ["reviews", "reddit", "user opinions"]):
        prompt_delta["prefer_domains"] = ["reddit.com", "wirecutter.com"]
        rationale += "Preferring review sites; "
    
    return {
        "policy_delta": policy_delta,
        "prompt_delta": prompt_delta,
        "rationale": rationale.rstrip("; ") or "User feedback applied"
    }


def generate_patch(trace: list, feedback: dict, max_retries: int = 3) -> dict:
    """
    Generate a patch based on feedback using LLM with validation and retry logic.
    Falls back to rule-based patch if LLM fails after retries.
    
    Args:
        trace: Execution trace from the run
        feedback: User feedback with tags and notes
        max_retries: Number of retry attempts for LLM
    
    Returns:
        dict with policy_delta, prompt_delta, and rationale
    """
    
    # Prepare feedback summary for better LLM understanding
    tags = feedback.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except:
            tags = []
    
    notes = feedback.get("notes", "") or ""
    
    feedback_summary = {
        "tags": tags,
        "notes": notes,
        "tag_count": len(tags)
    }
    
    # Try LLM generation with retries
    for attempt in range(max_retries):
        try:
            print(f"[LEARN] Attempt {attempt + 1}/{max_retries} to generate patch")
            
            llm = get_chat_model()
            parser = JsonOutputParser(pydantic_object=LearnOutput)
            prompt = PromptTemplate(
                template=LEARNER_PROMPT,
                input_variables=["trace", "feedback"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )
            
            # Truncate trace to avoid token limits but keep important parts
            trace_str = json.dumps(trace, indent=2)
            if len(trace_str) > 12000:
                # Keep first and last parts of trace
                trace_str = trace_str[:6000] + "\n... (truncated) ...\n" + trace_str[-6000:]
            
            feedback_str = json.dumps(feedback_summary, indent=2)
            
            message = prompt.format(
                trace=trace_str,
                feedback=feedback_str
            )
            
            # Invoke LLM
            response = llm.invoke(message)
            text = response.content if hasattr(response, "content") else str(response)
            
            # Parse and validate
            parsed = parser.parse(text)
            
            # Ensure we have a LearnOutput instance
            if isinstance(parsed, dict):
                patch = LearnOutput(**parsed)
            else:
                patch = parsed
            
            result = patch.model_dump()
            
            # Validate the result is not empty
            if not result.get("policy_delta") and not result.get("prompt_delta"):
                print(f"[LEARN] Attempt {attempt + 1}: Empty patch generated, retrying...")
                if attempt < max_retries - 1:
                    continue
                else:
                    raise ValueError("LLM generated empty patch after all retries")
            
            print(f"[LEARN] Successfully generated patch:")
            print(f"[LEARN]   policy_delta: {result.get('policy_delta')}")
            print(f"[LEARN]   prompt_delta: {result.get('prompt_delta')}")
            print(f"[LEARN]   rationale: {result.get('rationale')}")
            
            return result
            
        except Exception as e:
            print(f"[LEARN] Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"[LEARN] Retrying...")
                continue
            else:
                print(f"[LEARN] All LLM attempts failed, using fallback patch")
                import traceback
                traceback.print_exc()
    
    # If all retries failed, use fallback
    fallback = _generate_fallback_patch(feedback)
    print(f"[LEARN] Using fallback patch: {fallback}")
    return fallback
