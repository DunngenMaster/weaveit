import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client


router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_200_OK)
async def submit_feedback(request: FeedbackRequest):
    try:
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store feedback: {str(e)}"
        )
