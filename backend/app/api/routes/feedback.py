import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.agent.learn import generate_patch
from app.services.weaviate_client import weaviate_client
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client


router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_200_OK)
async def submit_feedback(request: FeedbackRequest):
    try:
        print(f"[FEEDBACK] Received: run_id={request.run_id}, tab_id={request.tab_id}")
        client = redis_client.get_client()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis connection unavailable"
            )
        
        feedback = {
            "run_id": request.run_id,
            "tab_id": request.tab_id,
            "tags": json.dumps(request.tags),
            "notes": request.notes or "",
            "ts": str(int(datetime.now().timestamp() * 1000))
        }
        
        feedback_key = f"run:{request.run_id}:feedback"
        client.hset(feedback_key, mapping=feedback)
        client.expire(feedback_key, 86400)
        
        tab_feedback_key = f"tab:{request.tab_id}:feedback"
        client.rpush(tab_feedback_key, json.dumps(feedback))
        client.ltrim(tab_feedback_key, -20, -1)
        client.expire(tab_feedback_key, 86400)
        
        # Generate patch if trace exists
        trace_key = f"run:{request.run_id}"
        run_data = client.hgetall(trace_key) or {}
        trace = []
        if run_data.get("trace"):
            try:
                trace = json.loads(run_data.get("trace", "[]"))
            except Exception:
                trace = []
        
        if trace:
            try:
                print(f"[FEEDBACK] ========== GENERATING PATCH ==========")
                print(f"[FEEDBACK] Run ID: {request.run_id}")
                print(f"[FEEDBACK] Tab ID: {request.tab_id}")
                print(f"[FEEDBACK] Tags: {request.tags}")
                print(f"[FEEDBACK] Notes: {request.notes}")
                print(f"[FEEDBACK] Trace length: {len(trace)} events")
                
                # Generate patch with retry logic
                patch = generate_patch(trace, feedback, max_retries=3)
                
                # Validate patch structure
                if not isinstance(patch, dict):
                    raise ValueError(f"Invalid patch type: {type(patch)}")
                
                if "policy_delta" not in patch or "prompt_delta" not in patch or "rationale" not in patch:
                    raise ValueError(f"Patch missing required fields: {patch.keys()}")
                
                print(f"[FEEDBACK] ========== PATCH GENERATED ==========")
                print(f"[FEEDBACK] policy_delta: {json.dumps(patch.get('policy_delta'), indent=2)}")
                print(f"[FEEDBACK] prompt_delta: {json.dumps(patch.get('prompt_delta'), indent=2)}")
                print(f"[FEEDBACK] rationale: {patch.get('rationale')}")
                
                # Save to Redis
                patch_json = json.dumps(patch)
                timestamp = str(int(datetime.now().timestamp() * 1000))
                
                patch_key = f"run:{request.run_id}:patch"
                client.hset(patch_key, mapping={"patch": patch_json, "ts": timestamp})
                client.expire(patch_key, 86400)
                print(f"[FEEDBACK] ✓ Saved to {patch_key}")
                
                tab_patch_key = f"tab:{request.tab_id}:patch"
                client.hset(tab_patch_key, mapping={"patch": patch_json, "ts": timestamp})
                client.expire(tab_patch_key, 86400)
                print(f"[FEEDBACK] ✓ Saved to {tab_patch_key}")
                
                # Verify save
                verification = client.hgetall(tab_patch_key)
                if verification and verification.get("patch"):
                    saved_patch = json.loads(verification.get("patch"))
                    print(f"[FEEDBACK] ✓ Verified: {saved_patch.get('policy_delta')}")
                else:
                    raise ValueError("Patch verification failed")
                
                print(f"[FEEDBACK] ========== SUCCESS ==========")
                
            except Exception as patch_error:
                print(f"[FEEDBACK] ========== ERROR ==========")
                print(f"[FEEDBACK] {patch_error}")
                import traceback
                traceback.print_exc()
            
            # Persist patch to Weaviate RunMemory for global recall
            try:
                if weaviate_client.client.is_ready() and weaviate_client.client.collections.exists("RunMemory"):
                    run_data = client.hgetall(trace_key) or {}
                    collection = weaviate_client.client.collections.get("RunMemory")
                    collection.data.insert({
                        "run_id": request.run_id,
                        "goal": run_data.get("goal", ""),
                        "query": run_data.get("query", ""),
                        "summary_text": "",
                        "policy_json": run_data.get("policy_json", "{}"),
                        "prompt_delta_json": run_data.get("prompt_delta", "{}"),
                        "patch_json": json.dumps(patch),
                        "metrics_json": run_data.get("metrics", "{}"),
                        "created_at": datetime.now(timezone.utc)
                    })
            except Exception as e:
                print(f"Error writing patch memory: {e}")
        
        try:
            wclient = weaviate_client.client
            if wclient.is_ready() and wclient.collections.exists("RunFeedback"):
                collection = wclient.collections.get("RunFeedback")
                collection.data.insert({
                    "run_id": request.run_id,
                    "tab_id": request.tab_id,
                    "tags": request.tags,
                    "notes": request.notes or "",
                    "created_at": datetime.now(timezone.utc)
                })
        except Exception as e:
            print(f"Error writing RunFeedback to Weaviate: {e}")
        
        return FeedbackResponse(ok=True)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"[FEEDBACK] Unhandled error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store feedback: {str(e)}"
        )
