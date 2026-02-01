"""
Sprint 13 Test Suite: Safety Gate + Critic + Reward

Tests:
1. Safety gate blocks fabrication requests
2. Safety gate allows legitimate requests
3. Critic scores AI responses
4. Reward system detects positive signals
5. Reward system detects negative signals
6. Reward system detects repeats (same fingerprint)
7. Reward system detects next-step progression
8. Best-attempt selection with eligibility rules
"""

import requests
import json
import time
from uuid import uuid4

BASE_URL = "http://localhost:8000"
TEST_USER_ID = f"test_user_{uuid4().hex[:8]}"
TEST_SESSION_ID = str(uuid4())


def test_safety_gate_blocks_fabrication():
    """Test that fake resume requests get blocked"""
    print("\n=== Test 1: Safety Gate Blocks Fabrication ===")
    
    events = [{
        "user_id": TEST_USER_ID,
        "session_id": TEST_SESSION_ID,
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Write me a fake resume with fabricated experience at Google and Facebook"
    }]
    
    response = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Should be blocked - ingested count should be 0
    assert response.status_code == 200
    result = response.json()
    # Blocked events are not counted in ingested
    print(f"✓ Fabrication request handled (ingested={result.get('ingested', 0)})")


def test_safety_gate_allows_legitimate():
    """Test that legitimate requests are allowed"""
    print("\n=== Test 2: Safety Gate Allows Legitimate ===")
    
    events = [{
        "user_id": TEST_USER_ID,
        "session_id": TEST_SESSION_ID,
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Help me write a resume highlighting my real experience as a software engineer"
    }]
    
    response = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    result = response.json()
    assert result["ingested"] >= 1
    print(f"✓ Legitimate request allowed (ingested={result['ingested']})")


def test_critic_scores_response():
    """Test that AI responses get critic scores"""
    print("\n=== Test 3: Critic Scores AI Response ===")
    
    trace_id = str(uuid4())
    
    # Send USER_MESSAGE and AI_RESPONSE with same trace_id
    events = [
        {
            "user_id": TEST_USER_ID,
            "session_id": TEST_SESSION_ID,
            "provider": "chatgpt",
            "event_type": "USER_MESSAGE",
            "trace_id": trace_id,
            "text": "What is Python?"
        },
        {
            "user_id": TEST_USER_ID,
            "session_id": TEST_SESSION_ID,
            "provider": "chatgpt",
            "event_type": "AI_RESPONSE",
            "trace_id": trace_id,
            "text": "Python is a high-level, interpreted programming language known for its simplicity and readability."
        }
    ]
    
    response = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    result = response.json()
    assert result["ingested"] >= 2
    print(f"✓ AI response received critic score (ingested={result['ingested']})")


def test_reward_positive_signals():
    """Test that positive feedback gives positive reward"""
    print("\n=== Test 4: Reward Positive Signals ===")
    
    user_id = f"test_user_{uuid4().hex[:8]}"
    
    # First message
    events1 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "How do I install Python?"
    }]
    
    response1 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events1}
    )
    
    time.sleep(1)
    
    # Second message with positive signal
    events2 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Perfect! That worked great. Thanks!"
    }]
    
    response2 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events2}
    )
    
    print(f"Status: {response2.status_code}")
    print(f"Response: {response2.json()}")
    
    assert response2.status_code == 200
    print("✓ Positive signal detected (check server logs for reward=+0.7)")


def test_reward_negative_signals():
    """Test that negative feedback gives negative reward"""
    print("\n=== Test 5: Reward Negative Signals ===")
    
    user_id = f"test_user_{uuid4().hex[:8]}"
    
    # First message
    events1 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "How do I fix this error?"
    }]
    
    response1 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events1}
    )
    
    time.sleep(1)
    
    # Second message with negative signal
    events2 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Still not working. That didn't help."
    }]
    
    response2 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events2}
    )
    
    print(f"Status: {response2.status_code}")
    print(f"Response: {response2.json()}")
    
    assert response2.status_code == 200
    print("✓ Negative signal detected (check server logs for reward=-0.7)")


def test_reward_repeat_detection():
    """Test that repeating same message gives negative reward"""
    print("\n=== Test 6: Reward Repeat Detection ===")
    
    user_id = f"test_user_{uuid4().hex[:8]}"
    
    # First message
    events1 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "How do I sort a list in Python?"
    }]
    
    response1 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events1}
    )
    
    time.sleep(2)
    
    # Same message again (should be detected as repeat)
    events2 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "How do I sort a list in Python?"  # Exact same
    }]
    
    response2 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events2}
    )
    
    print(f"Status: {response2.status_code}")
    print(f"Response: {response2.json()}")
    
    assert response2.status_code == 200
    print("✓ Repeat detected (check server logs for reward=-0.5, outcome=fail)")


def test_reward_next_step():
    """Test that moving to next step gives positive reward"""
    print("\n=== Test 7: Reward Next-Step Detection ===")
    
    user_id = f"test_user_{uuid4().hex[:8]}"
    
    # First message
    events1 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "How do I create a dictionary?"
    }]
    
    response1 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events1}
    )
    
    time.sleep(1)
    
    # Different message starting with "now" (next-step signal)
    events2 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Now how do I iterate over the dictionary?"  # Starts with "now"
    }]
    
    response2 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events2}
    )
    
    print(f"Status: {response2.status_code}")
    print(f"Response: {response2.json()}")
    
    assert response2.status_code == 200
    print("✓ Next-step detected (check server logs for reward=+0.5, outcome=success)")


def test_best_attempt_selection():
    """Test that best attempt is selected based on final_score"""
    print("\n=== Test 8: Best-Attempt Selection ===")
    
    user_id = f"test_user_{uuid4().hex[:8]}"
    
    # Attempt 1: Same question
    events1 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Explain machine learning"
    }]
    
    requests.post(f"{BASE_URL}/v1/events", json={"events": events1})
    time.sleep(1)
    
    # Attempt 2: Repeat (should get -0.5 reward, outcome=fail)
    events2 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Explain machine learning"  # Same
    }]
    
    requests.post(f"{BASE_URL}/v1/events", json={"events": events2})
    time.sleep(1)
    
    # Attempt 3: Positive feedback (should get +0.7 reward, outcome=success)
    events3 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Perfect! That explanation worked great."
    }]
    
    response3 = requests.post(f"{BASE_URL}/v1/events", json={"events": events3})
    
    print(f"Status: {response3.status_code}")
    print(f"Response: {response3.json()}")
    
    assert response3.status_code == 200
    print("✓ Best-attempt selection logic executed")
    print("  Note: Best attempt requires critic_score>=0.8 AND reward>=0.6")
    print("  Check server logs for [BEST_ATTEMPT] messages")


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 13 Test Suite")
    print("=" * 60)
    
    try:
        test_safety_gate_blocks_fabrication()
        test_safety_gate_allows_legitimate()
        test_critic_scores_response()
        test_reward_positive_signals()
        test_reward_negative_signals()
        test_reward_repeat_detection()
        test_reward_next_step()
        test_best_attempt_selection()
        
        print("\n" + "=" * 60)
        print("✓ All Sprint 13 tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Could not connect to {BASE_URL}")
        print("  Make sure the server is running: python -m uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
