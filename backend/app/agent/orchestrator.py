import json
from datetime import datetime, timezone
from app.agent.graph import build_agent_graph
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client


def _write_trace_to_weaviate(run_id: str, tab_id: str, goal: str, query: str, status: str, trace: list[dict]):
    try:
        client = weaviate_client.client
        if not client.is_ready():
            return False
        if not client.collections.exists("RunTrace"):
            return False
        collection = client.collections.get("RunTrace")
        now = datetime.now(timezone.utc)
        collection.data.insert({
            "run_id": run_id,
            "tab_id": tab_id,
            "goal": goal,
            "query": query,
            "status": status,
            "trace_json": json.dumps(trace),
            "created_at": now
        })
        return True
    except Exception as e:
        print(f"Error writing RunTrace to Weaviate: {e}")
        return False


def run_agent(run_id: str, goal: str, query: str, limit: int, tab_id: str, url: str | None):
    client = redis_client.get_client()
    graph = build_agent_graph()
    
    state = {
        "run_id": run_id,
        "goal": goal,
        "query": query,
        "limit": limit,
        "tab_id": tab_id,
        "url": url,
        "status": "running",
        "plan": None,
        "browserbase_session_id": None,
        "connect_url": None,
        "candidate_links": [],
        "extracted_items": [],
        "trace": []
    }
    
    try:
        result = graph.invoke(state)
        status = result.get("status", "completed")
        trace = result.get("trace", [])
        extracted_items = result.get("extracted_items", [])
        candidate_links = result.get("candidate_links", [])
        plan = result.get("plan")
        
        run_key = f"run:{run_id}"
        client.hset(run_key, mapping={
            "status": status,
            "completed_at": str(int(datetime.now().timestamp() * 1000)),
            "plan": json.dumps(plan or {}),
            "trace": json.dumps(trace),
            "extracted": json.dumps(extracted_items),
            "candidates": json.dumps(candidate_links)
        })
        client.expire(run_key, 86400)
        
        prefs_key = f"tab:{tab_id}:preferences"
        client.hset(prefs_key, mapping={
            "last_run_id": run_id,
            "last_status": status
        })
        client.expire(prefs_key, 86400)
        
        _write_trace_to_weaviate(run_id, tab_id, goal, query, status, trace)
        return True
    except Exception as e:
        run_key = f"run:{run_id}"
        client.hset(run_key, mapping={
            "status": "error",
            "error": str(e)
        })
        client.expire(run_key, 86400)
        print(f"Run failed: {e}")
        return False
