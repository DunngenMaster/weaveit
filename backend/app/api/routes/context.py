from fastapi import APIRouter, Query
from app.schemas.context import ContextResponse
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client
import weaviate.classes as wvc


router = APIRouter(prefix="/v1/context")


def build_context_block(
    active_goal: str,
    summaries: list[str],
    next_steps: list[str],
    memories: list[dict]
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
    """
    
    client = redis_client.client
    weaviate_cli = weaviate_client.client
    
    # Find most recent session for this user
    # For now, we'll use a simple pattern - in production you'd track active sessions
    session_pattern = f"session:*:state"
    
    # Get active goal from most recent session state
    # Simplified: just use user_id as session identifier for now
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
    
    # Query Weaviate for top 8 relevant memories
    memories = []
    try:
        collection = weaviate_cli.collections.get("MemoryItem")
        
        # Build filter for user_id and active status
        filters = wvc.query.Filter.by_property("user_id").equal(user_id) & \
                  wvc.query.Filter.by_property("status").equal("active")
        
        # If page_type provided, could add tag filtering here
        # For now, just get top memories by confidence
        
        result = collection.query.fetch_objects(
            filters=filters,
            limit=8
        )
        
        for obj in result.objects:
            props = obj.properties
            memories.append({
                'kind': props.get('kind', ''),
                'key': props.get('key', ''),
                'text': props.get('text', ''),
                'tags': props.get('tags', []),
                'confidence': props.get('confidence', 0)
            })
    
    except Exception as e:
        print(f"Error querying Weaviate: {e}")
        # Continue with empty memories
    
    # Extract next_steps from summaries or use empty list
    next_steps = []
    # TODO: Could extract from last extraction result if we store it
    
    # Build context block
    context_block = build_context_block(
        active_goal=active_goal,
        summaries=summaries,
        next_steps=next_steps,
        memories=memories
    )
    
    return ContextResponse(
        context_block=context_block,
        active_goal=active_goal,
        next_steps=next_steps
    )
