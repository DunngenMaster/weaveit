import json
from datetime import datetime, timezone
from app.agent.graph import build_agent_graph
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client
import weaviate.classes as wvc


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


def _write_run_memory(run_id: str, goal: str, query: str, summary: dict, policy: dict, prompt_delta: dict, patch: dict, metrics: dict):
    try:
        client = weaviate_client.client
        if not client.is_ready():
            return False
        if not client.collections.exists("RunMemory"):
            return False
        collection = client.collections.get("RunMemory")
        now = datetime.now(timezone.utc)
        summary_text = ""
        if summary:
            rec = summary.get("recommendation", {})
            summary_text = f"Top pick: {rec.get('name','')}. Reason: {rec.get('reason','')}"
        
        # Check if a RunMemory with this run_id already exists (from feedback)
        # If it does and has a patch, don't overwrite it
        try:
            existing = collection.query.fetch_objects(
                filters=wvc.query.Filter.by_property("run_id").equal(run_id),
                limit=1
            )
            if existing.objects and existing.objects[0].properties.get("patch_json"):
                existing_patch = json.loads(existing.objects[0].properties.get("patch_json", "{}"))
                if existing_patch.get("policy_delta") or existing_patch.get("prompt_delta"):
                    print(f"[RunMemory] Skipping write for {run_id} - already has feedback patch")
                    return True
        except Exception as check_error:
            print(f"[RunMemory] Error checking existing: {check_error}")
        
        collection.data.insert({
            "run_id": run_id,
            "goal": goal,
            "query": query,
            "summary_text": summary_text,
            "policy_json": json.dumps(policy or {}),
            "prompt_delta_json": json.dumps(prompt_delta or {}),
            "patch_json": json.dumps(patch or {}),
            "metrics_json": json.dumps(metrics or {}),
            "created_at": now
        })
        return True
    except Exception as e:
        print(f"Error writing RunMemory to Weaviate: {e}")
        return False


def run_agent(run_id: str, goal: str, query: str, limit: int, tab_id: str, url: str | None, policy: dict | None, prompt_delta: dict | None):
    client = redis_client.get_client()
    graph = build_agent_graph()
    
    started_at_ms = int(datetime.now().timestamp() * 1000)
    state = {
        "run_id": run_id,
        "goal": goal,
        "query": query,
        "limit": limit,
        "tab_id": tab_id,
        "url": url,
        "started_at_ms": started_at_ms,
        "status": "running",
        "status_reason": None,
        "plan": None,
        "policy": policy or {},
        "prompt_delta": prompt_delta or {},
        "browserbase_session_id": None,
        "connect_url": None,
        "live_view_url": None,
        "candidate_links": [],
        "extracted_items": [],
        "summary": None,
        "trace": []
    }
    
    try:
        # Emit run_started event
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "run_started", "payload": {"ts": started_at_ms}})
        )
        client.expire(f"run:{run_id}:events", 86400)
        
        result = graph.invoke(state)
        status = result.get("status", "completed")
        status_reason = result.get("status_reason")
        trace = result.get("trace", [])
        extracted_items = result.get("extracted_items", [])
        summary = result.get("summary", {})
        candidate_links = result.get("candidate_links", [])
        connect_url = result.get("connect_url")
        live_view_url = result.get("live_view_url")
        plan = result.get("plan")
        metrics = {
            "candidates": len(candidate_links),
            "extracted": len(extracted_items),
            "tabs_opened": len(candidate_links),
            "status": status
        }
        
        run_key = f"run:{run_id}"
        client.hset(run_key, mapping={
            "status": status,
            "status_reason": status_reason or "",
            "completed_at": str(int(datetime.now().timestamp() * 1000)),
            "plan": json.dumps(plan or {}),
            "trace": json.dumps(trace),
            "extracted": json.dumps(extracted_items),
            "candidates": json.dumps(candidate_links),
            "connect_url": connect_url or "",
            "live_view_url": live_view_url or "",
            "summary": json.dumps(summary or {}),
            "metrics": json.dumps(metrics)
        })
        client.expire(run_key, 86400)
        
        prefs_key = f"tab:{tab_id}:preferences"
        client.hset(prefs_key, mapping={
            "last_run_id": run_id,
            "last_status": status
        })
        client.expire(prefs_key, 86400)
        
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "run_completed", "payload": {"status": status}})
        )
        client.expire(f"run:{run_id}:events", 86400)
        
        _write_trace_to_weaviate(run_id, tab_id, goal, query, status, trace)
        
        # Retrieve patch if feedback was submitted
        patch_from_redis = {}
        patch_key = f"run:{run_id}:patch"
        patch_data = client.hgetall(patch_key) or {}
        if patch_data.get("patch"):
            try:
                patch_from_redis = json.loads(patch_data.get("patch", "{}"))
            except Exception:
                pass
        
        _write_run_memory(run_id, goal, query, summary, policy or {}, prompt_delta or {}, patch_from_redis, metrics)
        return True
    except Exception as e:
        run_key = f"run:{run_id}"
        client.hset(run_key, mapping={
            "status": "error",
            "error": str(e)
        })
        client.expire(run_key, 86400)
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "run_error", "payload": {"error": str(e)}})
        )
        client.expire(f"run:{run_id}:events", 86400)
        print(f"Run failed: {e}")
        return False
