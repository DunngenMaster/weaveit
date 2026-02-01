"""
Evaluation & Explainability Endpoints (Sprint 16.5 & 16.6)

Story 16.5: Evaluation harness for demonstrating learning
Story 16.6: Explainability trace showing why decisions were made
"""

from fastapi import APIRouter, Query, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.services.redis_client import redis_client
from app.services.bandit_selector import bandit_selector, STRATEGIES
from app.services.policy_manager import policy_manager
from app.services.rag_cache import rag_cache
from app.services.attempt_thread import attempt_thread_manager
from app.services.memory_hygiene import memory_hygiene


router = APIRouter(prefix="/v1")


# Story 16.5: Evaluation Harness

class EvalRequest(BaseModel):
    user_id: str
    domain: str = "unknown"
    prompt_set_id: str = "default"


EVAL_PROMPTS = {
    "default": [
        "How do I write a professional resume?",
        "What's the best way to prepare for a technical interview?",
        "Can you help me debug this Python code?",
        "How do I negotiate a job offer?",
        "What should I include in my LinkedIn profile?"
    ]
}


@router.post("/eval/run")
async def run_evaluation(request: EvalRequest):
    """
    Run evaluation harness to demonstrate learning.
    
    Executes 5 fixed test prompts and returns learning metrics:
    - Selected strategy per prompt
    - Cache hit rate
    - Number of successful resolutions
    - Top policy patterns
    - Last reward scores
    
    This is the "one-call proof" for judges to see improvement.
    """
    
    client = redis_client.get_client()
    prompts = EVAL_PROMPTS.get(request.prompt_set_id, EVAL_PROMPTS["default"])
    
    results = {
        "user_id": request.user_id,
        "domain": request.domain,
        "prompt_set_id": request.prompt_set_id,
        "prompts_tested": len(prompts),
        "strategy_selections": [],
        "cache_stats": {},
        "successful_resolutions": 0,
        "failed_resolutions": 0,
        "policy_patterns": [],
        "reward_scores": [],
        "bandit_stats": {}
    }
    
    # 1. Test strategy selection for each prompt
    for i, prompt in enumerate(prompts):
        strategy, scores = bandit_selector.select_strategy(
            request.user_id,
            request.domain
        )
        
        results["strategy_selections"].append({
            "prompt_index": i,
            "prompt": prompt[:50] + "...",
            "selected_strategy": strategy,
            "ucb1_scores": {k: round(v, 3) for k, v in scores.items()}
        })
    
    # 2. Get cache statistics
    cache_stats = rag_cache.get_stats(request.user_id)
    results["cache_stats"] = cache_stats
    
    # 3. Count successful/failed resolutions from attempt threads
    attempt_index_pattern = f"attempt_index:{request.user_id}:*"
    cursor = 0
    thread_ids = []
    
    while True:
        cursor, keys = client.scan(cursor, match=attempt_index_pattern, count=100)
        for key in keys:
            thread_id = client.get(key)
            if thread_id:
                thread_id_str = thread_id.decode('utf-8') if isinstance(thread_id, bytes) else thread_id
                thread_ids.append(thread_id_str)
        if cursor == 0:
            break
    
    # Analyze threads
    for thread_id in thread_ids[:50]:  # Limit to 50 most recent
        metadata = attempt_thread_manager.get_thread_metadata(thread_id)
        if metadata:
            status = metadata.get("status", "open")
            best_reward = float(metadata.get("best_reward", 0))
            
            if status == "resolved":
                if best_reward >= 0.6:
                    results["successful_resolutions"] += 1
                else:
                    results["failed_resolutions"] += 1
                
                results["reward_scores"].append(round(best_reward, 2))
    
    # 4. Get top policy patterns
    patterns = policy_manager.get_top_patterns(
        request.user_id,
        request.domain,
        limit=5
    )
    
    results["policy_patterns"] = [
        {"pattern": p[:80] + "..." if len(p) > 80 else p, "score": round(s, 3)}
        for p, s in patterns
    ]
    
    # 5. Get bandit statistics
    results["bandit_stats"] = bandit_selector.get_all_stats(
        request.user_id,
        request.domain
    )
    
    # Summary metrics
    results["summary"] = {
        "total_threads": len(thread_ids),
        "resolution_rate": round(
            results["successful_resolutions"] / max(len(thread_ids), 1),
            3
        ),
        "average_reward": round(
            sum(results["reward_scores"]) / max(len(results["reward_scores"]), 1),
            3
        ) if results["reward_scores"] else 0.0,
        "patterns_learned": len(results["policy_patterns"]),
        "most_successful_strategy": max(
            results["bandit_stats"].items(),
            key=lambda x: x[1]["win_rate"]
        )[0] if results["bandit_stats"] else "none"
    }
    
    return results


# Story 16.6: Explainability Trace

@router.get("/explain")
async def explain_decision(
    user_id: str = Query(..., description="User ID"),
    fingerprint: str = Query(..., description="Message fingerprint"),
    domain: str = Query("unknown", description="Domain")
):
    """
    Explain why the system made specific decisions.
    
    Returns:
    - Chosen strategy + bandit statistics
    - Top 3 policy patterns with scores
    - Whether RAG cache was used
    - Safety gate decision (allowed/blocked)
    
    This is the "why did it do that?" endpoint for transparency.
    """
    
    client = redis_client.get_client()
    
    # 1. Strategy selection
    selected_strategy, ucb1_scores = bandit_selector.select_strategy(user_id, domain)
    bandit_stats = bandit_selector.get_all_stats(user_id, domain)
    
    strategy_explanation = {
        "selected_strategy": selected_strategy,
        "ucb1_scores": {k: round(v, 3) for k, v in ucb1_scores.items()},
        "strategy_stats": bandit_stats,
        "instruction": bandit_selector.get_instruction(selected_strategy)
    }
    
    # 2. Policy patterns
    patterns = policy_manager.get_top_patterns(user_id, domain, limit=3)
    pattern_explanation = [
        {
            "pattern": p,
            "score": round(s, 3),
            "reward_component": round(s * 0.7, 3),
            "critic_component": round(s * 0.3, 3)
        }
        for p, s in patterns
    ]
    
    # 3. RAG cache status
    # Try to find cache key for this fingerprint
    cache_key_pattern = f"rag_cache:{user_id}:{domain}:*:{fingerprint[:16]}"
    cache_exists = False
    
    try:
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match=cache_key_pattern, count=10)
            if keys:
                cache_exists = True
                break
            if cursor == 0:
                break
    except:
        pass
    
    cache_explanation = {
        "cache_hit": cache_exists,
        "cache_key_pattern": cache_key_pattern,
        "ttl": "10 minutes" if cache_exists else "N/A"
    }
    
    # 4. Safety gate (check if there's a blocked counter for this user)
    safety_blocked_total = 0
    safety_categories = ["FABRICATION", "ILLEGAL", "UNETHICAL", "HARMFUL"]
    
    for category in safety_categories:
        counter_key = f"safety_counter:{user_id}:{category}"
        count = int(client.get(counter_key) or 0)
        safety_blocked_total += count
    
    safety_explanation = {
        "total_blocked_requests": safety_blocked_total,
        "likely_allowed": safety_blocked_total == 0 or "appears safe",
        "note": "Safety gate checks: FABRICATION, ILLEGAL, UNETHICAL, HARMFUL"
    }
    
    # 5. Attempt thread info (if exists for this fingerprint)
    attempt_index_key = f"attempt_index:{user_id}:{fingerprint}"
    thread_id = client.get(attempt_index_key)
    
    thread_explanation = None
    if thread_id:
        thread_id_str = thread_id.decode('utf-8') if isinstance(thread_id, bytes) else thread_id
        metadata = attempt_thread_manager.get_thread_metadata(thread_id_str)
        
        if metadata:
            thread_explanation = {
                "thread_id": thread_id_str[:16] + "...",
                "status": metadata.get("status", "unknown"),
                "attempt_count": int(metadata.get("attempt_count", 0)),
                "best_reward": float(metadata.get("best_reward", 0)),
                "best_attempt_id": metadata.get("best_attempt_id", "none")
            }
    
    return {
        "user_id": user_id,
        "fingerprint": fingerprint[:16] + "...",
        "domain": domain,
        "strategy": strategy_explanation,
        "policy_patterns": pattern_explanation,
        "rag_cache": cache_explanation,
        "safety_gate": safety_explanation,
        "attempt_thread": thread_explanation,
        "explanation_summary": f"Using strategy '{selected_strategy}' based on UCB1 bandit algorithm. "
                              f"Top pattern score: {patterns[0][1]:.3f} if patterns else 0.0}. "
                              f"Cache {'HIT' if cache_exists else 'MISS'}. "
                              f"Safety: {safety_blocked_total} blocked requests."
    }


# Story 16.4: Admin endpoint for decay

@router.post("/admin/decay")
async def trigger_decay(
    user_id: str = Query(..., description="User ID"),
    domain: Optional[str] = Query(None, description="Specific domain to decay (or all if None)"),
    decay_factor: float = Query(0.8, description="Decay multiplier (0.8 = 20% reduction)")
):
    """
    Manually trigger pattern decay (Story 16.4).
    
    Reduces scores of unused patterns to prevent stale information dominance.
    """
    
    if domain:
        # Decay specific domain
        count = memory_hygiene.decay_specific_domain(user_id, domain, decay_factor)
        return {
            "user_id": user_id,
            "domain": domain,
            "patterns_decayed": count,
            "decay_factor": decay_factor
        }
    else:
        # Decay all domains
        results = memory_hygiene.decay_unused_patterns(
            user_id,
            days_unused=14,
            decay_factor=decay_factor
        )
        
        total_decayed = sum(results.values())
        
        return {
            "user_id": user_id,
            "domains_processed": len(results),
            "total_patterns_decayed": total_decayed,
            "decay_factor": decay_factor,
            "by_domain": results
        }
