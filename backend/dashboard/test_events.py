"""
Dashboard Event Test Script

Sends test events to dashboard to verify WebSocket streaming works.
Run this while dashboard is running to see live updates.
"""

import asyncio
import httpx
import random
import time


DASHBOARD_URL = "http://localhost:8001"

# Test events
TEST_EVENTS = [
    {
        "event_type": "bandit_selection",
        "strategy": "S1_CLARIFY_FIRST",
        "domain": "resume",
        "user_id": "test_user_123",
        "ucb_scores": {
            "S1_CLARIFY_FIRST": 2.456,
            "S2_THREE_VARIANTS": 1.823,
            "S3_TEMPLATE_FIRST": 1.234,
            "S4_STEPWISE": 0.987
        }
    },
    {
        "event_type": "judge_evaluation",
        "run_id": "run_456",
        "score": 0.87,
        "violations": [],
        "reasons": ["Excellent clarity", "Good specificity"],
        "criteria": "quality_compliance"
    },
    {
        "event_type": "reward_update",
        "run_id": "run_456",
        "strategy": "S1_CLARIFY_FIRST",
        "reward": 0.7,
        "total_rewards": 12,
        "outcome": "success",
        "reason": "positive_signal:worked"
    },
    {
        "event_type": "csa_created",
        "csa_id": "abc-123-def",
        "title": "Software Engineer Job Search",
        "user_id": "test_user_123",
        "source_provider": "chatgpt",
        "trigger": "session_length"
    },
    {
        "event_type": "memory_write",
        "kind": "GOAL",
        "key": "find_remote_job",
        "confidence": 0.92,
        "text_preview": "User wants to find remote software engineer positions"
    }
]


async def send_test_events():
    """Send test events to dashboard API"""
    
    print("🧪 Sending test events to dashboard...")
    print(f"   Dashboard: {DASHBOARD_URL}")
    print("")
    
    async with httpx.AsyncClient() as client:
        # Check if dashboard is running
        try:
            resp = await client.get(f"{DASHBOARD_URL}/api/stats")
            print(f"✅ Dashboard is running: {resp.json()}")
            print("")
        except:
            print("❌ Dashboard not running! Start it first with: python -m uvicorn dashboard.app:app --port 8001")
            return
        
        # Send test events in a loop
        for i in range(20):
            # Pick random event
            event = random.choice(TEST_EVENTS).copy()
            
            # Randomize some values
            if event["event_type"] == "bandit_selection":
                event["ucb_scores"] = {
                    k: round(random.uniform(0.5, 3.0), 3)
                    for k in event["ucb_scores"].keys()
                }
            elif event["event_type"] == "judge_evaluation":
                event["score"] = round(random.uniform(0.5, 1.0), 2)
            elif event["event_type"] == "reward_update":
                event["reward"] = random.choice([0.7, -0.7, 0.5, -0.5, 0.0])
                event["total_rewards"] = random.randint(1, 50)
            
            # Send event
            try:
                resp = await client.post(
                    f"{DASHBOARD_URL}/api/events/publish",
                    json=event
                )
                result = resp.json()
                print(f"📡 Sent {event['event_type']} → {result['clients_notified']} clients notified")
            except Exception as e:
                print(f"❌ Error sending event: {e}")
            
            # Wait a bit between events
            await asyncio.sleep(random.uniform(0.5, 2.0))
    
    print("")
    print("✅ Test completed! Check your dashboard browser window.")


if __name__ == "__main__":
    asyncio.run(send_test_events())
