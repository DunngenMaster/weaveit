from fastapi import APIRouter, Query
from app.schemas.context import ContextResponse
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client
from app.services.bandit_selector import STRATEGY_INSTRUCTIONS
import weaviate.classes as wvc
import json
from datetime import datetime


router = APIRouter(prefix="/v1/context")


def build_context_block(
    active_goal: str,
    summaries: list[str],
    next_steps: list[str],
    memories: list[dict],
    selected_strategy: str = None
) -> str:
    """Build formatted context block for injection into provider"""
    
    # Group memories by kind
    preferences = [m for m in memories if m.get('kind') == 'PREFERENCE']
    goals = [m for m in memories if m.get('kind') == 'GOAL']
    constraints = [m for m in memories if m.get('kind') == 'CONSTRAINT']
    decisions = [m for m in memories if m.get('kind') == 'DECISION']
    artifacts = [m for m in memories if m.get('kind') == 'ARTIFACT']
    profile = [m for m in memories if m.get('kind') == 'PROFILE']
    
    # Build context block sections
    lines = ["MEMORY_SNAPSHOT:", ""]
    
    # ACTIVE_GOAL section
    lines.append("ACTIVE_GOAL:")
    if active_goal:
        lines.append(f"  {active_goal}")
    else:
        lines.append("  None set")
    lines.append("")
    
    # SELECTED_STRATEGY section (from bandit learning)
    if selected_strategy and selected_strategy in STRATEGY_INSTRUCTIONS:
        lines.append("SELECTED_STRATEGY:")
        strategy_text = STRATEGY_INSTRUCTIONS[selected_strategy]
        for line in strategy_text.split('\n'):
            lines.append(f"  {line}")
        lines.append("")
    
    # WHAT_WE_DID section (from summaries)
    lines.append("WHAT_WE_DID:")
    if summaries:
        for summary in summaries[-5:]:  # Last 5 summaries
            if summary and summary != "TURN_RECEIVED":
                lines.append(f"  - {summary}")
    else:
        lines.append("  No recent activity")
    lines.append("")
    
    # NEXT_STEPS section
    lines.append("NEXT_STEPS:")
    if next_steps:
        for step in next_steps:
            lines.append(f"  - {step}")
    else:
        lines.append("  None planned")
    lines.append("")
    
    # PREFERENCES section
    lines.append("PREFERENCES:")
    if preferences:
        for pref in preferences:
            lines.append(f"  - {pref.get('text', '')}")
    if constraints:
        for cons in constraints:
            lines.append(f"  - {cons.get('text', '')}")
    if not preferences and not constraints:
        lines.append("  None recorded")
    lines.append("")
    
    # Add other memory types if present
    if goals:
        lines.append("REMEMBERED_GOALS:")
        for goal in goals:
            lines.append(f"  - {goal.get('text', '')}")
        lines.append("")
    
    if decisions:
        lines.append("PAST_DECISIONS:")
        for dec in decisions:
            lines.append(f"  - {dec.get('text', '')}")
        lines.append("")
    
    if artifacts:
        lines.append("ARTIFACTS:")
        for art in artifacts:
            lines.append(f"  - {art.get('key', '')}: {art.get('text', '')}")
        lines.append("")
    
    if profile:
        lines.append("USER_PROFILE:")
        for prof in profile:
            lines.append(f"  - {prof.get('text', '')}")
        lines.append("")
    
    return "\n".join(lines)


@router.get("", response_model=ContextResponse)
async def get_context(
    user_id: str = Query(..., description="User identifier"),
    provider: str = Query(..., description="Provider (chatgpt, claude, gemini, etc.)"),
    page_type: str = Query(None, description="Page type for filtering memories"),
    url: str = Query(None, description="Current URL")
):
    """
    Get context for continuing where user left off.
    
    Returns formatted context block with:
    - Active goal
    - Recent summaries
    - Next steps
    - Relevant memories
    
    Sprint 17.3: Always returns something via last_good_context fallback
    """
    
    client = redis_client.client
    weaviate_cli = weaviate_client.client
    
    # Try to build fresh context
    try:
        # Get active goal from most recent session state
        state_key = f"session:{user_id}:state"
        active_goal = ""
        if client.exists(state_key):
            active_goal = client.hget(state_key, "goal") or ""
            if isinstance(active_goal, bytes):
                active_goal = active_goal.decode()
        
        # Get last 5 summaries
        summaries_key = f"session:{user_id}:summaries"
        summaries = []
        if client.exists(summaries_key):
            raw_summaries = client.lrange(summaries_key, -5, -1)
            summaries = [s.decode() if isinstance(s, bytes) else s for s in raw_summaries]
        
        # Query Weaviate for top 8 relevant memories using hybrid search
        # Sprint 17.4: Hybrid search with alpha=0.6 (favor vector) + max distance threshold
        memories = []
        collection = weaviate_cli.collections.get("MemoryItem")
        
        # Build filter for user_id and active status
        filters = wvc.query.Filter.by_property("user_id").equal(user_id) & \
                  wvc.query.Filter.by_property("status").equal("active")
        
        # Build keyword query from context
        keyword_terms = []
        if page_type:
            keyword_terms.append(page_type)
        if active_goal:
            keyword_terms.extend(active_goal.split()[:3])  # First 3 words of goal
        
        query_text = " ".join(keyword_terms) if keyword_terms else "work preferences goals"
        
        # Hybrid search: alpha=0.6 favors vector similarity over keyword matching
        # max_vector_distance prevents irrelevant matches from polluting context
        result = collection.query.hybrid(
            query=query_text,
            alpha=0.6,  # 0.6 = favor vector, 0.4 = keyword weight
            limit=8,
            filters=filters,
            return_metadata=wvc.query.MetadataQuery(distance=True)
        )
        
        for obj in result.objects:
            # Filter by max vector distance (reject junk matches)
            # Distance < 0.5 = very similar, > 0.8 = likely irrelevant
            if obj.metadata.distance and obj.metadata.distance > 0.75:
                continue  # Skip low-quality matches
            
            props = obj.properties
            memories.append({
                'kind': props.get('kind', ''),
                'key': props.get('key', ''),
                'text': props.get('text', ''),
                'tags': props.get('tags', []),
                'confidence': props.get('confidence', 0),
                'distance': obj.metadata.distance if obj.metadata.distance else 0.0
            })
        
        # Extract next_steps from summaries or use empty list
        next_steps = []
        # TODO: Could extract from last extraction result if we store it
        
        # Get selected strategy from recent events (last 5 events)
        selected_strategy = None
        events_key = f"events:{user_id}:{provider}"
        if client.exists(events_key):
            recent_events = client.lrange(events_key, 0, 4)  # Last 5 events
            for event_json in recent_events:
                try:
                    event_str = event_json.decode() if isinstance(event_json, bytes) else event_json
                    event = json.loads(event_str)
                    payload = event.get('payload', {})
                    if 'selected_strategy' in payload:
                        selected_strategy = payload['selected_strategy']
                        break  # Use most recent strategy
                except:
                    continue
        
        # Build context block with strategy injection
        context_block = build_context_block(
            active_goal=active_goal,
            summaries=summaries,
            next_steps=next_steps,
            memories=memories,
            selected_strategy=selected_strategy
        )
        
        # Store as last_good_context (24h TTL)
        last_good_key = f"last_good_context:{user_id}:{provider}"
        good_context = {
            'context_block': context_block,
            'active_goal': active_goal,
            'next_steps': next_steps,
            'generated_at': datetime.now().isoformat()
        }
        client.setex(last_good_key, 24 * 60 * 60, json.dumps(good_context))
        
        return ContextResponse(
            context_block=context_block,
            active_goal=active_goal,
            next_steps=next_steps
        )
    
    except Exception as e:
        print(f"Error building fresh context: {e}")
        
        # FALLBACK: Try to load last_good_context
        last_good_key = f"last_good_context:{user_id}:{provider}"
        cached = client.get(last_good_key)
        
        if cached:
            try:
                if isinstance(cached, bytes):
                    cached = cached.decode()
                cached_data = json.loads(cached)
                
                print(f"[CONTEXT_FALLBACK] Using cached context from {cached_data.get('generated_at')}")
                
                return ContextResponse(
                    context_block=cached_data.get('context_block', ''),
                    active_goal=cached_data.get('active_goal', ''),
                    next_steps=cached_data.get('next_steps', [])
                )
            except Exception as cache_err:
                print(f"Error loading cached context: {cache_err}")
        
        # FINAL FALLBACK: Return minimal context
        print("[CONTEXT_FALLBACK] Returning minimal context")
        minimal_context = build_context_block(
            active_goal="",
            summaries=[],
            next_steps=[],
            memories=[]
        )
        
        return ContextResponse(
            context_block=minimal_context,
            active_goal="",
            next_steps=[]
        )
