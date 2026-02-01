from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from datetime import datetime
from uuid import uuid4
import json
from app.schemas.runs import RunStartRequest, RunStartResponse, LearnedResponse, RunDetailsResponse
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client
from app.agent.orchestrator import run_agent


router = APIRouter()


@router.post("/runs", response_model=RunStartResponse, status_code=status.HTTP_200_OK)
async def start_run(request: RunStartRequest, background_tasks: BackgroundTasks):
    """
    Start a new agent run.
    
    This is a lightweight stub that records run metadata in Redis.
    """
    try:
        client = redis_client.get_client()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis connection unavailable"
            )
        
        run_id = str(uuid4())
        started_at = int(datetime.now().timestamp() * 1000)
        
        run_key = f"run:{run_id}"
        run_payload = {
            "run_id": run_id,
            "status": "started",
            "goal": request.goal,
            "query": request.query,
            "limit": str(request.limit),
            "tab_id": request.tab_id,
            "url": request.url or "",
            "started_at": str(started_at)
        }
        client.hset(run_key, mapping=run_payload)
        client.expire(run_key, 86400)

        policy = {
            "max_tabs": "11",
            "min_score": "0.55",
            "unique_domains": "1",
            "max_time_ms": "120000"
        }
        prompt_delta = {}
        patch_key = f"tab:{request.tab_id}:patch"
        patch_data = client.hgetall(patch_key) or {}
        if patch_data.get("patch"):
            try:
                patch = json.loads(patch_data.get("patch", "{}"))
                policy_delta = patch.get("policy_delta", {}) or {}
                prompt_delta = patch.get("prompt_delta", {}) or {}
                for key, value in policy_delta.items():
                    if value is None:
                        continue
                    if key in policy:
                        policy[key] = str(value)
            except Exception:
                pass
        else:
            try:
                memories = weaviate_client.search_run_memory(
                    f"{request.goal} {request.query}",
                    limit=1
                )
                if memories:
                    mem = memories[0]
                    # Load learned patch if it exists
                    patch_json = mem.get("patch_json") or "{}"
                    prompt_json = mem.get("prompt_delta_json") or "{}"
                    learned_patch = json.loads(patch_json)
                    prompt_delta = json.loads(prompt_json)
                    
                    # Apply policy_delta from the learned patch
                    policy_delta = learned_patch.get("policy_delta", {}) or {}
                    for key, value in policy_delta.items():
                        if key in policy and value is not None:
                            policy[key] = str(value)
                    
                    # Also merge prompt_delta from patch if exists
                    patch_prompt_delta = learned_patch.get("prompt_delta", {}) or {}
                    prompt_delta.update(patch_prompt_delta)
            except Exception as e:
                print(f"Error loading learned memory: {e}")
                pass
        policy_key = f"run:{run_id}:policy"
        client.hset(policy_key, mapping=policy)
        client.expire(policy_key, 86400)
        
        tab_policy_key = f"tab:{request.tab_id}:policy"
        client.hset(tab_policy_key, mapping=policy)
        client.expire(tab_policy_key, 86400)

        client.hset(run_key, mapping={
            "policy_json": json.dumps(policy),
            "prompt_delta": json.dumps(prompt_delta)
        })
        
        tab_runs_key = f"tab:{request.tab_id}:runs"
        client.rpush(tab_runs_key, run_id)
        client.ltrim(tab_runs_key, -50, -1)
        client.expire(tab_runs_key, 86400)
        
        prefs_key = f"tab:{request.tab_id}:preferences"
        client.hset(prefs_key, mapping={
            "last_goal": request.goal,
            "last_query": request.query,
            "last_url": request.url or "",
            "last_run_id": run_id,
            "last_status": "started",
            "policy_max_tabs": policy["max_tabs"],
            "policy_min_score": policy["min_score"],
            "policy_unique_domains": policy["unique_domains"],
            "policy_max_time_ms": policy["max_time_ms"],
            "prompt_delta": json.dumps(prompt_delta)
        })
        client.expire(prefs_key, 86400)
        
        background_tasks.add_task(
            run_agent,
            run_id,
            request.goal,
            request.query,
            request.limit,
            request.tab_id,
            request.url,
            policy,
            prompt_delta
        )
        
        return RunStartResponse(run_id=run_id, status="started")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start run: {str(e)}"
        )


@router.get("/learned", response_model=LearnedResponse)
async def get_learned(tab_id: str):
    """
    Return learned preferences for a given tab.
    """
    try:
        client = redis_client.get_client()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis connection unavailable"
            )
        
        prefs_key = f"tab:{tab_id}:preferences"
        prefs = client.hgetall(prefs_key) or {}
        return LearnedResponse(preferences=prefs)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load learned preferences: {str(e)}"
        )


@router.get("/runs/{run_id}", response_model=RunDetailsResponse)
async def get_run_details(run_id: str):
    try:
        client = redis_client.get_client()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis connection unavailable"
            )
        
        run_key = f"run:{run_id}"
        data = client.hgetall(run_key) or {}
        if not data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Run not found"
            )
        
        plan = {}
        trace = []
        extracted = []
        candidates = []
        summary = {}
        patch = {}
        applied_policy = {}
        applied_prompt_delta = {}
        metrics = {}
        if data.get("plan"):
            try:
                plan = json.loads(data.get("plan", "{}"))
            except Exception:
                plan = {}
        if data.get("trace"):
            try:
                trace = json.loads(data.get("trace", "[]"))
            except Exception:
                trace = []
        if data.get("extracted"):
            try:
                extracted = json.loads(data.get("extracted", "[]"))
            except Exception:
                extracted = []
        if data.get("candidates"):
            try:
                candidates = json.loads(data.get("candidates", "[]"))
            except Exception:
                candidates = []
        if data.get("summary"):
            try:
                summary = json.loads(data.get("summary", "{}"))
            except Exception:
                summary = {}
        if data.get("metrics"):
            try:
                metrics = json.loads(data.get("metrics", "{}"))
            except Exception:
                metrics = {}
        patch_key = f"run:{run_id}:patch"
        patch_data = client.hgetall(patch_key) or {}
        if patch_data.get("patch"):
            try:
                patch = json.loads(patch_data.get("patch", "{}"))
            except Exception:
                patch = {}
        if data.get("policy_json"):
            try:
                applied_policy = json.loads(data.get("policy_json", "{}"))
            except Exception:
                applied_policy = {}
        if data.get("prompt_delta"):
            try:
                applied_prompt_delta = json.loads(data.get("prompt_delta", "{}"))
            except Exception:
                applied_prompt_delta = {}
        
        return RunDetailsResponse(
            run_id=run_id,
            status=data.get("status", "unknown"),
            status_reason=data.get("status_reason") or None,
            goal=data.get("goal"),
            query=data.get("query"),
            error=data.get("error"),
            plan=plan or {},
            candidates=candidates or [],
            extracted=extracted or [],
            trace=trace or [],
            connect_url=data.get("connect_url") or None,
            live_view_url=data.get("live_view_url") or None,
            summary=summary or {},
            patch=patch or {},
            applied_policy=applied_policy or {},
            applied_prompt_delta=applied_prompt_delta or {},
            metrics=metrics or {}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load run details: {str(e)}"
        )
