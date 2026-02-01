"""
Live Dashboard - Real-time System Monitoring

Standalone FastAPI app (Port 8001) showing:
- Bandit arm selections (live UCB scores)
- Judge evaluations happening
- Strategy performance over time
- Reward tracking
- Memory operations
- CSA creations

NO FALLBACKS - Everything streams in real-time via WebSocket
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
import asyncio
import json
import time
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path


# Global event queue for live streaming
event_queue: asyncio.Queue = asyncio.Queue()
active_connections: List[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔴 Live Dashboard starting on http://localhost:8001")
    print("📊 Open browser to see real-time system activity")
    yield
    print("Dashboard shutting down...")


app = FastAPI(
    title="WeavelT Live Dashboard",
    description="Real-time visualization of self-improving AI system",
    version="1.0.0",
    lifespan=lifespan
)

# Serve static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve dashboard HTML"""
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Dashboard UI not found. Creating...</h1>")


@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for live event streaming.
    
    Clients connect here and receive real-time events:
    - bandit_selection: {strategy, domain, ucb_scores, timestamp}
    - judge_evaluation: {run_id, score, criteria, timestamp}
    - reward_update: {run_id, reward, total_rewards, timestamp}
    - strategy_change: {old, new, reason, timestamp}
    - memory_write: {kind, key, confidence, timestamp}
    - csa_created: {csa_id, title, trigger, timestamp}
    """
    await websocket.accept()
    active_connections.append(websocket)
    print(f"✅ Dashboard client connected. Total clients: {len(active_connections)}")
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "event_type": "connection",
            "message": "Connected to live event stream",
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep connection alive and send events
        while True:
            try:
                # Wait for events from queue (non-blocking with timeout)
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                
                # Broadcast to this client
                await websocket.send_json(event)
                
            except asyncio.TimeoutError:
                # Send heartbeat every second to keep connection alive
                await websocket.send_json({
                    "event_type": "heartbeat",
                    "timestamp": datetime.now().isoformat()
                })
                
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print(f"❌ Dashboard client disconnected. Remaining: {len(active_connections)}")


@app.post("/api/events/publish")
async def publish_event(event: Dict[str, Any]):
    """
    API endpoint for main backend to publish events to dashboard.
    
    Called by bandit_selector, critic, reward system, etc.
    """
    # Add timestamp if not present
    if "timestamp" not in event:
        event["timestamp"] = datetime.now().isoformat()
    
    # Put in queue for all WebSocket clients
    await event_queue.put(event)
    
    # Also broadcast immediately to all connected clients
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(event)
        except:
            disconnected.append(connection)
    
    # Clean up disconnected clients
    for conn in disconnected:
        if conn in active_connections:
            active_connections.remove(conn)
    
    return {
        "status": "published",
        "event_type": event.get("event_type"),
        "clients_notified": len(active_connections)
    }


@app.get("/api/stats")
async def get_stats():
    """Current dashboard stats"""
    return {
        "active_connections": len(active_connections),
        "queue_size": event_queue.qsize(),
        "uptime_seconds": time.time(),
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
