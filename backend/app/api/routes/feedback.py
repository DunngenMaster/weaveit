import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.agent.learn import generate_patch
from app.services.weaviate_client import weaviate_client
from app.services.redis_client import redis_client


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
                print(f"[FEEDBACK] Generating patch for run {request.run_id}")
                patch = generate_patch(trace, feedback)
                patch_key = f"run:{request.run_id}:patch"
                client.hset(patch_key, mapping={
                    "patch": json.dumps(patch),
                    "ts": str(int(datetime.now().timestamp() * 1000))
                })
                client.expire(patch_key, 86400)
                
                tab_patch_key = f"tab:{request.tab_id}:patch"
                client.hset(tab_patch_key, mapping={
                    "patch": json.dumps(patch),
                    "ts": str(int(datetime.now().timestamp() * 1000))
                })
                client.expire(tab_patch_key, 86400)
                print("[FEEDBACK] Patch generated and saved")
                
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
                    print(f"[FEEDBACK] Error writing patch memory: {e}")
            except Exception as patch_error:
                print(f"[FEEDBACK] Error generating patch: {patch_error}")
                import traceback
                traceback.print_exc()
        
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
