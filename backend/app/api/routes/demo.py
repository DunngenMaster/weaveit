from fastapi import APIRouter, HTTPException
from app.schemas.demo import JobToContextRequest, JobToContextResponse
from app.services.redis_client import redis_client
from app.api.routes.browser import extract_job_posting
from app.api.routes.context import get_context
from app.schemas.browser import ExtractJobRequest


router = APIRouter(prefix="/v1/demo")


@router.post("/job_to_context", response_model=JobToContextResponse)
async def job_to_context(request: JobToContextRequest):
    """
    One-shot endpoint: Extract job posting and return context block.
    
    Combines job extraction with context generation for immediate use.
    """
    
    # Step 1: Extract job posting
    extract_request = ExtractJobRequest(
        user_id=request.user_id,
        browserbase_session_id=request.browserbase_session_id,
        url=request.job_url
    )
    
    try:
        extract_result = await extract_job_posting(extract_request)
        job_data = extract_result.extracted
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Job extraction failed: {str(e)}"
        )
    
    # Step 2: Update working memory with active job
    client = redis_client.client
    state_key = f"session:{request.user_id}:state"
    client.hset(state_key, "active_job", job_data.get("job_title", ""))
    client.hset(state_key, "goal", f"Apply to {job_data.get('job_title', '')} at {job_data.get('company', '')}")
    
    # Step 3: Get context block
    try:
        context_result = await get_context(
            user_id=request.user_id,
            provider=request.provider,
            page_type="job_posting",
            url=request.job_url
        )
        context_block = context_result.context_block
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Context generation failed: {str(e)}"
        )
    
    return JobToContextResponse(
        context_block=context_block,
        job=job_data
    )
