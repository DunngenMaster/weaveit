"""
Debug and Metrics Endpoint (Sprint 15.6)

Provides visibility into self-improvement: attempt threads, learned patterns,
reward scores, cache stats. Hackathon-ready observability.
"""

from fastapi import APIRouter, Query
from typing import Optional
from app.services.redis_client import redis_client
from app.services.attempt_thread import attempt_thread_manager
from app.services.policy_manager import policy_manager
from app.services.rag_cache import rag_cache
from app.services.context_bundle import context_bundle_manager


router = APIRouter(prefix="/v1/debug")


@router.get("/state")
async def get_debug_state(user_id: str = Query(..., description="User ID to inspect")):
    """
    Get comprehensive debug state for a user.
    
    Shows:
    - Metrics (attempts, resolved threads, blocked requests, promotions)
    - Open vs resolved attempt threads
    - Top learned skill patterns by domain
    - Last reward scores
    - Cache hit/miss stats
    - Context bundle status
    
    This is the "show the agent improving" endpoint for demos.
    """
    
    client = redis_client.get_client()
    
    # Metrics counters
    metrics = {
        "attempts": int(client.get(f"metrics:attempts:{user_id}") or 0),
        "resolved_threads": int(client.get(f"metrics:resolved_threads:{user_id}") or 0),
        "blocked_requests": int(client.get(f"metrics:blocked_requests:{user_id}") or 0),
        "skill_promotions": int(client.get(f"metrics:skill_promotions:{user_id}") or 0)
    }
    
    # Attempt threads summary
    # Find all attempt threads for user
    attempt_index_pattern = f"attempt_index:{user_id}:*"
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
    
    # Get thread metadata
    threads_open = 0
    threads_resolved = 0
    recent_rewards = []
    
    for thread_id in thread_ids[:20]:  # Limit to 20 most recent
        metadata = attempt_thread_manager.get_thread_metadata(thread_id)
        if metadata:
            status = metadata.get("status", "open")
            if status == "resolved":
                threads_resolved += 1
                best_reward = float(metadata.get("best_reward", 0))
                recent_rewards.append(best_reward)
            else:
                threads_open += 1
    
    threads_summary = {
        "total_tracked": len(thread_ids),
        "open": threads_open,
        "resolved": threads_resolved,
        "recent_rewards": recent_rewards[-10:]  # Last 10
    }
    
    # Policy patterns
    policy_stats = policy_manager.get_stats(user_id)
    
    # Top patterns by domain
    top_patterns_by_domain = {}
    for domain in policy_stats.get("patterns_by_domain", {}).keys():
        patterns = policy_manager.get_top_patterns(user_id, domain, limit=5)
        top_patterns_by_domain[domain] = [
            {"pattern": p, "score": round(s, 3)}
            for p, s in patterns
        ]
    
    # RAG cache stats
    cache_stats = rag_cache.get_stats(user_id)
    
    # Context bundle
    bundle = context_bundle_manager.get_bundle(user_id)
    bundle_summary = {
        "exists": bundle is not None,
        "has_goal": bool(bundle and bundle.get("active_goal")),
        "has_task": bool(bundle and bundle.get("active_task")),
        "summaries_count": len(bundle.get("last_5_session_summaries", [])) if bundle else 0,
        "skill_patterns_count": len(bundle.get("top_skill_patterns", [])) if bundle else 0,
        "updated_ts": bundle.get("updated_ts") if bundle else None
    }
    
    return {
        "user_id": user_id,
        "metrics": metrics,
        "attempt_threads": threads_summary,
        "learned_policies": {
            "total_domains": policy_stats.get("total_domains", 0),
            "patterns_by_domain": policy_stats.get("patterns_by_domain", {}),
            "top_patterns": top_patterns_by_domain
        },
        "cache": cache_stats,
        "context_bundle": bundle_summary
    }


@router.get("/metrics")
async def get_metrics(user_id: str = Query(..., description="User ID")):
    """
    Get just the metrics counters (lightweight).
    """
    client = redis_client.get_client()
    
    return {
        "user_id": user_id,
        "attempts": int(client.get(f"metrics:attempts:{user_id}") or 0),
        "resolved_threads": int(client.get(f"metrics:resolved_threads:{user_id}") or 0),
        "blocked_requests": int(client.get(f"metrics:blocked_requests:{user_id}") or 0),
        "skill_promotions": int(client.get(f"metrics:skill_promotions:{user_id}") or 0)
    }


@router.get("/patterns")
async def get_patterns(
    user_id: str = Query(..., description="User ID"),
    domain: str = Query("unknown", description="Domain to query")
):
    """
    Get learned patterns for a specific domain.
    """
    patterns = policy_manager.get_top_patterns(user_id, domain, limit=10)
    
    return {
        "user_id": user_id,
        "domain": domain,
        "patterns": [
            {"pattern": p, "score": round(s, 3)}
            for p, s in patterns
        ]
    }


@router.get("/bundle")
async def get_bundle(user_id: str = Query(..., description="User ID")):
    """
    Get context bundle for user.
    """
    bundle = context_bundle_manager.get_bundle(user_id)
    
    if not bundle:
        return {"user_id": user_id, "bundle": None}
    
    return {
        "user_id": user_id,
        "bundle": bundle
    }
