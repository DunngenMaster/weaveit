"""
Dashboard Event Publisher

Singleton client to publish events to live dashboard.
Used by bandit_selector, critic, reward, memory_writer, etc.
"""

import httpx
import asyncio
from typing import Dict, Any
from datetime import datetime


class DashboardPublisher:
    """Publishes events to live dashboard via HTTP POST (non-blocking)"""
    
    def __init__(self, dashboard_url: str = "http://localhost:8001"):
        self.dashboard_url = dashboard_url
        self.enabled = True  # Can be disabled if dashboard not running
    
    async def publish(self, event_type: str, data: Dict[str, Any]):
        """
        Publish event to dashboard (async, non-blocking).
        
        Args:
            event_type: Type of event (bandit_selection, judge_evaluation, etc.)
            data: Event data dictionary
        """
        if not self.enabled:
            return
        
        event = {
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            **data
        }
        
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                await client.post(
                    f"{self.dashboard_url}/api/events/publish",
                    json=event
                )
        except Exception as e:
            # Silent fail - dashboard might not be running
            # Don't let dashboard issues break main backend
            pass
    
    def publish_sync(self, event_type: str, data: Dict[str, Any]):
        """Synchronous version - creates event loop if needed"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, schedule task
                asyncio.create_task(self.publish(event_type, data))
            else:
                # Run in new loop
                loop.run_until_complete(self.publish(event_type, data))
        except:
            # Fallback: create new loop
            try:
                asyncio.run(self.publish(event_type, data))
            except:
                pass  # Silent fail


# Global singleton
dashboard = DashboardPublisher()
