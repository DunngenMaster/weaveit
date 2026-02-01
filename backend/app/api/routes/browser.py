from fastapi import APIRouter, HTTPException, status
from app.schemas.browser import (
    BrowserSessionStartRequest,
    BrowserSessionStartResponse,
    ExtractJobRequest,
    ExtractJobResponse
)
from app.schemas.events import Event, EventBatch
from app.services.browserbase_client import browserbase_client
from app.services.redis_client import redis_client
from app.services.page_classifier import classify_page
from app.api.routes.events import ingest_events
from datetime import datetime


router = APIRouter(prefix="/v1/browser")


@router.post("/session/start", response_model=BrowserSessionStartResponse)
async def start_browser_session(request: BrowserSessionStartRequest):
    """
    Start a new Browserbase session for a user.
    
    Creates session, stores mapping in Redis, and ingests SESSION_START event.
    """
    
    # Create Browserbase session
    result = browserbase_client.create_session(request.user_id)
    
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Browserbase session: {result.get('error')}"
        )
    
    session_id = result.get("session_id")
    
    # Store mapping in Redis with 24h TTL
    client = redis_client.client
    mapping_key = f"user:{request.user_id}:browser_session_id"
    client.setex(mapping_key, 86400, session_id)
    
    # Create internal SESSION_START event
    event = Event(
        user_id=request.user_id,
        session_id=session_id,
        provider="browserbase",
        event_type="NAVIGATE",  # Use NAVIGATE as closest valid type
        ts=int(datetime.now().timestamp() * 1000),
        payload={"browserbase_session_id": session_id, "action": "SESSION_START"}
    )
    
    # Ingest event internally
    try:
        await ingest_events(EventBatch(events=[event]))
    except Exception as e:
        print(f"Warning: Failed to ingest SESSION_START event: {e}")
    
    return BrowserSessionStartResponse(
        session_id=session_id,
        status="created"
    )


@router.post("/extract/job", response_model=ExtractJobResponse)
async def extract_job_posting(request: ExtractJobRequest):
    """
    Extract structured job posting data from a URL.
    
    Validates URL is a job posting, extracts data via Browserbase,
    and ingests as PAGE_EXTRACT event.
    """
    
    # Classify page type
    page_type = classify_page(request.url, None)
    
    if page_type != "job_posting":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "URL_NOT_JOB_POSTING"}
        )
    
    # Run extraction via Browserbase
    result = browserbase_client.run_extraction(
        request.browserbase_session_id,
        request.url,
        extract_type="job_posting"
    )
    
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {result.get('error')}"
        )
    
    # Extract payload data
    extracted_data = result.get("data", {})
    payload = {
        "job_title": extracted_data.get("job_title", ""),
        "company": extracted_data.get("company", ""),
        "location": extracted_data.get("location", ""),
        "employment_type": extracted_data.get("employment_type"),
        "skills": extracted_data.get("skills", []),
        "summary_text": extracted_data.get("summary_text", "")
    }
    
    # Create PAGE_EXTRACT event
    event = Event(
        user_id=request.user_id,
        session_id=request.browserbase_session_id,
        provider="browserbase",
        event_type="PAGE_EXTRACT",
        url=request.url,
        ts=int(datetime.now().timestamp() * 1000),
        payload=payload
    )
    
    # Ingest event
    try:
        await ingest_events(EventBatch(events=[event]))
    except Exception as e:
        print(f"Warning: Failed to ingest PAGE_EXTRACT event: {e}")
    
    return ExtractJobResponse(
        ok=True,
        extracted=payload
    )
