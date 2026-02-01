import asyncio
import json
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from app.services.redis_client import redis_client


router = APIRouter()


async def _event_stream(run_id: str):
    client = redis_client.get_client()
    if not client:
        yield "event: error\ndata: {}\n\n"
        return
    
    key = f"run:{run_id}:events"
    last_index = 0
    
    while True:
        try:
            events = client.lrange(key, last_index, -1) or []
            if events:
                for item in events:
                    try:
                        payload = json.loads(item)
                    except Exception:
                        payload = {"type": "event", "payload": {"raw": item}}
                    yield f"data: {json.dumps(payload)}\n\n"
                last_index += len(events)
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception:
            yield "event: error\ndata: {}\n\n"
            await asyncio.sleep(1)


@router.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str):
    client = redis_client.get_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis connection unavailable"
        )
    
    return StreamingResponse(
        _event_stream(run_id),
        media_type="text/event-stream"
    )
