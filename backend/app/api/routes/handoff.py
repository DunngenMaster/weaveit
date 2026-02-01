"""
Story 18.6 & 18.7: Handoff API Endpoints

Endpoints:
- POST /v1/handoff/csa/create - Create CSA manually
- GET /v1/handoff/csa/latest - Get latest CSA metadata
- GET /v1/handoff/csa/file - Download CSA file
- POST /v1/handoff/attach - Browserbase auto-attach integration
"""

import base64
import json
from fastapi import APIRouter, Query, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.services.csa_builder_v2 import csa_builder
from app.services.csa_store import csa_store
from app.services.handoff_detector import handoff_detector
from app.services.weaviate_client import weaviate_client
from app.services.safety_gate import safety_gate


router = APIRouter(prefix="/v1/handoff", tags=["handoff"])


class CreateCSARequest(BaseModel):
    """Request to create a CSA."""
    user_id: str
    source_provider: Optional[str] = "unknown"
    source_session_id: Optional[str] = "unknown"
    domain: Optional[str] = "unknown"


class AttachRequest(BaseModel):
    """Request to attach CSA to new chat (Browserbase integration)."""
    user_id: str
    browserbase_session_id: str
    provider: str  # chatgpt/claude/gemini
    chat_url: str


@router.post("/csa/create")
async def create_csa(request: CreateCSARequest):
    """
    Story 18.6: Create CSA manually (for debugging/demo).
    
    Also integrates Story 18.4 (Weaviate ArtifactSummary) and
    Story 18.8 (Safety guardrails).
    """
    try:
        # Story 18.8: Safety check - if previous request was blocked, generate minimal CSA
        safety_blocked_key = f"safety:blocked:{request.user_id}:recent"
        from app.services.redis_client import redis_client
        if redis_client.client.get(safety_blocked_key):
            print(f"[HANDOFF] User {request.user_id} has blocked content, generating minimal CSA")
            # Generate minimal CSA
            from uuid import uuid4
            import time
            from app.schemas.csa import ConversationSnapshotArtifact
            
            minimal_csa = ConversationSnapshotArtifact(
                csa_id=str(uuid4()),
                schema_version=1,
                user_id=request.user_id,
                created_ts_ms=int(time.time() * 1000),
                source_provider=request.source_provider,
                source_session_id=request.source_session_id,
                title="Safe Conversation Continuation",
                user_intent="Continue with safe alternatives",
                what_we_did=["Previous request blocked by safety system"],
                what_worked=[],
                what_failed=["Previous request contained disallowed content"],
                constraints=["All content must comply with safety policies"],
                preferences=[],
                key_entities={},
                artifacts=[],
                next_steps=["Continue conversation with safe alternatives"],
                instructions_for_next_model=[
                    "Previous request was blocked; continuing with safe alternatives",
                    "User is aware of safety policies"
                ]
            )
            csa = minimal_csa
        else:
            # Build CSA using Gemini
            csa = await csa_builder.build_csa(
                user_id=request.user_id,
                source_provider=request.source_provider,
                source_session_id=request.source_session_id,
                domain=request.domain
            )
        
        # Story 18.3: Save CSA to disk and Redis
        save_result = csa_store.save_csa(csa, save_markdown=True)
        
        # Story 18.4: Add Weaviate ArtifactSummary entry
        try:
            artifact_summary = {
                "user_id": request.user_id,
                "artifact_type": "conversation_snapshot",
                "artifact_id": csa.csa_id,
                "title": csa.title,
                "summary_text": f"CSA: {csa.user_intent}. Created from {csa.source_provider} session.",
                "created_at": csa.created_ts_ms,
                "tags": [csa.source_provider, request.domain, "csa", "handoff"]
            }
            
            # Store in Weaviate (reuse existing ArtifactSummary collection)
            weaviate_client.client.collections.get("ArtifactSummary").data.insert(
                properties=artifact_summary
            )
            print(f"[HANDOFF] Stored CSA {csa.csa_id} in Weaviate ArtifactSummary")
            
        except Exception as e:
            print(f"[HANDOFF] Warning: Could not store in Weaviate: {e}")
        
        # Clear handoff flag if it was set
        handoff_detector.clear_handoff_flag(request.user_id)
        
        return {
            "csa_id": csa.csa_id,
            "created_ts_ms": csa.created_ts_ms,
            "title": csa.title,
            "download_url": f"/v1/handoff/csa/file?csa_id={csa.csa_id}",
            "json_path": save_result["json_path"],
            "md_path": save_result["md_path"]
        }
        
    except Exception as e:
        import traceback
        print(f"[HANDOFF] CSA creation error: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"CSA creation failed: {str(e)}")


@router.get("/csa/latest")
async def get_latest_csa_metadata(user_id: str = Query(..., description="User identifier")):
    """
    Story 18.6: Get latest CSA metadata for user.
    """
    metadata = csa_store.get_latest_csa_metadata(user_id)
    
    if not metadata:
        raise HTTPException(status_code=404, detail="No CSA found for user")
    
    return metadata


@router.get("/csa/file")
async def download_csa_file(csa_id: str = Query(..., description="CSA identifier")):
    """
    Story 18.6: Download CSA file as JSON.
    """
    csa_bytes = csa_store.get_csa_file_bytes(csa_id)
    
    if not csa_bytes:
        raise HTTPException(status_code=404, detail="CSA file not found")
    
    # Return as downloadable JSON file
    return Response(
        content=csa_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=csa_{csa_id}.json"
        }
    )


@router.post("/attach")
async def attach_csa_to_chat(request: AttachRequest):
    """
    Story 18.7: Auto-attach CSA to new chat (Browserbase integration).
    
    Returns plan for Browserbase automation to attach CSA file.
    """
    try:
        # Get latest CSA metadata
        metadata = csa_store.get_latest_csa_metadata(request.user_id)
        
        if not metadata:
            return {
                "should_attach": False,
                "reason": "No CSA found for user",
                "preamble_text": None,
                "file_name": None,
                "file_bytes_base64": None
            }
        
        csa_id = metadata["csa_id"]
        
        # Get CSA file bytes
        csa_bytes = csa_store.get_csa_file_bytes(csa_id)
        
        if not csa_bytes:
            return {
                "should_attach": False,
                "reason": "CSA file not found in storage",
                "preamble_text": None,
                "file_name": None,
                "file_bytes_base64": None
            }
        
        # Convert to bytes if it's a string (from Redis decode_responses=True)
        if isinstance(csa_bytes, str):
            csa_bytes = csa_bytes.encode('utf-8')
        
        # Encode as base64 for transfer
        file_bytes_base64 = base64.b64encode(csa_bytes).decode('utf-8')
        
        # Generate preamble text
        preamble_text = (
            f"I've attached a context snapshot from my previous conversation. "
            f"Please review it and continue from where we left off. "
            f"The snapshot is titled: \"{metadata['title']}\""
        )
        
        return {
            "should_attach": True,
            "preamble_text": preamble_text,
            "file_name": f"csa_{csa_id}.json",
            "file_bytes_base64": file_bytes_base64,
            "csa_metadata": metadata
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Attach preparation failed: {str(e)}")


@router.get("/status")
async def get_handoff_status(user_id: str = Query(..., description="User identifier")):
    """
    Check if handoff is pending for user.
    """
    is_pending = handoff_detector.is_handoff_pending(user_id)
    
    metadata = None
    if not is_pending:
        # Check if CSA already exists
        metadata = csa_store.get_latest_csa_metadata(user_id)
    
    return {
        "user_id": user_id,
        "handoff_pending": is_pending,
        "latest_csa": metadata
    }
