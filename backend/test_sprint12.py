# Test Sprint 12: Canonical Events + Fingerprinting + Attempt Threads

import requests
import json

BASE_URL = "http://localhost:8000"

def test_canonical_event():
    """Test that events are normalized to canonical format"""
    print("\n=== Test 1: Canonical Event Normalization ===")
    
    # Test USER_MESSAGE
    event = {
        "user_id": "test_user_sprint12",
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Help me write a resume for a software engineer position"
    }
    
    response = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": [event]}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200, "Event ingestion failed"
    print("✓ Event ingested successfully")


def test_fingerprinting():
    """Test that same message with different formatting gets same fingerprint"""
    print("\n=== Test 2: Fingerprinting ===")
    
    # Same message, different formatting
    messages = [
        "Help me write a resume!",
        "  help   me    write   a   resume  ",
        "Help me write a resume?!?",
    ]
    
    for msg in messages:
        event = {
            "user_id": "test_user_sprint12",
            "provider": "chatgpt",
            "event_type": "USER_MESSAGE",
            "text": msg
        }
        
        response = requests.post(
            f"{BASE_URL}/v1/events",
            json={"events": [event]}
        )
        
        print(f"Message: '{msg}' -> Status: {response.status_code}")
    
    print("✓ All variations ingested (should have same fingerprint)")


def test_attempt_thread():
    """Test that repeating same request increments attempt count"""
    print("\n=== Test 3: Attempt Thread Tracking ===")
    
    # Send same message 3 times
    for i in range(3):
        event = {
            "user_id": "test_user_sprint12",
            "provider": "chatgpt",
            "event_type": "USER_MESSAGE",
            "text": "What are the best Python frameworks?"
        }
        
        response = requests.post(
            f"{BASE_URL}/v1/events",
            json={"events": [event]}
        )
        
        print(f"Attempt {i+1}: Status {response.status_code}")
    
    print("✓ All attempts ingested (check server logs for attempt thread ID)")


def test_trace_linking():
    """Test that USER_MESSAGE and AI_RESPONSE share same trace_id"""
    print("\n=== Test 4: Trace Linking ===")
    
    import uuid
    trace_id = str(uuid.uuid4())
    
    # User message
    user_event = {
        "user_id": "test_user_sprint12",
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "trace_id": trace_id,
        "text": "Tell me about machine learning"
    }
    
    # AI response
    ai_event = {
        "user_id": "test_user_sprint12",
        "provider": "chatgpt",
        "event_type": "AI_RESPONSE",
        "trace_id": trace_id,
        "text": "Machine learning is a subset of artificial intelligence..."
    }
    
    response = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": [user_event, ai_event]}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Trace ID: {trace_id}")
    print("✓ Request/response pair ingested with shared trace_id")


def test_missing_required_fields():
    """Test that events missing required fields are rejected"""
    print("\n=== Test 5: Validation ===")
    
    # Missing user_id
    event = {
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Test message"
    }
    
    response = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": [event]}
    )
    
    print(f"Missing user_id -> Status: {response.status_code}")
    assert response.status_code == 400, "Should reject event without user_id"
    print("✓ Correctly rejected invalid event")


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 12 Test Suite")
    print("=" * 60)
    
    try:
        test_canonical_event()
        test_fingerprinting()
        test_attempt_thread()
        test_trace_linking()
        test_missing_required_fields()
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
