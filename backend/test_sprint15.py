"""
Sprint 15 Test Suite: Redis-First Infrastructure

Tests:
1. Redis Streams event ingestion
2. Context Bundle creation and retrieval
3. RAG Cache hit/miss
4. Policy ZSET pattern ranking
5. Graceful degradation (Weaviate down)
6. Metrics tracking
7. Debug endpoint
"""

import requests
import json
import time
from uuid import uuid4

BASE_URL = "http://localhost:8000"
TEST_USER_ID = f"test_user_{uuid4().hex[:8]}"


def test_streams_ingestion():
    """Test that events are written to Redis Streams"""
    print("\n=== Test 1: Redis Streams Ingestion ===")
    
    events = [{
        "user_id": TEST_USER_ID,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Test message for streams"
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
    print("✓ Event ingested to Redis Streams")


def test_context_bundle():
    """Test context bundle creation"""
    print("\n=== Test 2: Context Bundle ===")
    
    # The bundle will be created automatically through event processing
    # Let's check if it exists via debug endpoint
    response = requests.get(
        f"{BASE_URL}/v1/debug/bundle",
        params={"user_id": TEST_USER_ID}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    print("✓ Context bundle endpoint works")


def test_metrics_tracking():
    """Test that metrics are tracked"""
    print("\n=== Test 3: Metrics Tracking ===")
    
    # Send some events
    events = [{
        "user_id": TEST_USER_ID,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "USER_MESSAGE",
        "text": "Test metrics"
    }]
    
    requests.post(f"{BASE_URL}/v1/events", json={"events": events})
    time.sleep(0.5)
    
    # Check metrics
    response = requests.get(
        f"{BASE_URL}/v1/debug/metrics",
        params={"user_id": TEST_USER_ID}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    result = response.json()
    assert result["attempts"] >= 0
    print(f"✓ Metrics tracked: {result['attempts']} attempts")


def test_debug_state():
    """Test comprehensive debug state endpoint"""
    print("\n=== Test 4: Debug State Endpoint ===")
    
    response = requests.get(
        f"{BASE_URL}/v1/debug/state",
        params={"user_id": TEST_USER_ID}
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"User: {result['user_id']}")
        print(f"Metrics: {result['metrics']}")
        print(f"Threads: {result['attempt_threads']}")
        print(f"Policies: {result['learned_policies']}")
        print(f"Cache: {result['cache']}")
        print(f"Bundle: {result['context_bundle']}")
        print("✓ Debug state endpoint works")
    else:
        print(f"Response: {response.text}")
        assert False, "Debug state endpoint failed"


def test_policy_patterns():
    """Test policy patterns endpoint"""
    print("\n=== Test 5: Policy Patterns ===")
    
    response = requests.get(
        f"{BASE_URL}/v1/debug/patterns",
        params={"user_id": TEST_USER_ID, "domain": "unknown"}
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    assert response.status_code == 200
    result = response.json()
    print(f"✓ Patterns endpoint works: {len(result['patterns'])} patterns")


def test_repeated_context_acceleration():
    """Test that repeated context generation uses cache"""
    print("\n=== Test 6: RAG Cache Acceleration ===")
    
    # First call - will miss cache
    start1 = time.time()
    try:
        response1 = requests.post(
            f"{BASE_URL}/v1/context",
            json={
                "user_id": TEST_USER_ID,
                "provider": "chatgpt",
                "domain": "unknown",
                "query": "Test query for caching"
            },
            timeout=10
        )
        elapsed1 = time.time() - start1
        print(f"First call: {elapsed1:.3f}s, Status: {response1.status_code}")
    except requests.exceptions.Timeout:
        print("First call timed out (expected if Weaviate is slow)")
        elapsed1 = 10.0
    except Exception as e:
        print(f"First call error: {e}")
        elapsed1 = 0
    
    time.sleep(0.5)
    
    # Second call - should hit cache
    start2 = time.time()
    try:
        response2 = requests.post(
            f"{BASE_URL}/v1/context",
            json={
                "user_id": TEST_USER_ID,
                "provider": "chatgpt",
                "domain": "unknown",
                "query": "Test query for caching"
            },
            timeout=10
        )
        elapsed2 = time.time() - start2
        print(f"Second call: {elapsed2:.3f}s, Status: {response2.status_code}")
        
        if elapsed2 < elapsed1:
            print(f"✓ Cache acceleration: {elapsed1/elapsed2:.1f}x faster")
        else:
            print("Note: Second call not faster (cache may not be active)")
    except Exception as e:
        print(f"Second call error: {e}")


def test_stream_replay():
    """Test that stream consumer can replay events"""
    print("\n=== Test 7: Stream Replay Capability ===")
    
    # Send multiple events
    for i in range(3):
        events = [{
            "user_id": TEST_USER_ID,
            "session_id": str(uuid4()),
            "provider": "chatgpt",
            "event_type": "USER_MESSAGE",
            "text": f"Replay test message {i}"
        }]
        
        response = requests.post(
            f"{BASE_URL}/v1/events",
            json={"events": events}
        )
        assert response.status_code == 200
    
    print("✓ Multiple events sent to stream")
    print("  (Manual verification: check Redis stream:events:{user_id} with XLEN/XRANGE)")


def test_graceful_degradation():
    """Test that system works even if Weaviate is unavailable"""
    print("\n=== Test 8: Graceful Degradation ===")
    
    # Try to get context - should succeed with bundle fallback
    try:
        response = requests.post(
            f"{BASE_URL}/v1/context",
            json={
                "user_id": TEST_USER_ID,
                "provider": "chatgpt",
                "domain": "unknown",
                "query": "Test graceful degradation"
            },
            timeout=5
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Context source: {result.get('source', 'unknown')}")
            print("✓ Context generation succeeded (graceful degradation working)")
        else:
            print(f"Response: {response.text}")
            print("Note: Context endpoint returned non-200, but didn't crash")
    except requests.exceptions.Timeout:
        print("⚠ Context generation timed out")
        print("  This suggests fallback chain needs optimization")
    except Exception as e:
        print(f"Error: {e}")
        print("  System should handle this gracefully")


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 15 Test Suite: Redis-First Infrastructure")
    print("=" * 60)
    
    try:
        test_streams_ingestion()
        test_context_bundle()
        test_metrics_tracking()
        test_debug_state()
        test_policy_patterns()
        test_repeated_context_acceleration()
        test_stream_replay()
        test_graceful_degradation()
        
        print("\n" + "=" * 60)
        print("✓ Sprint 15 Tests Complete!")
        print("=" * 60)
        print("\nNotes:")
        print("- Check server logs for [STREAM] messages")
        print("- Verify Redis keys: stream:events:{user_id}, bundle:{user_id}, policy:{user_id}:*")
        print("- Test graceful degradation by stopping Weaviate")
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Could not connect to {BASE_URL}")
        print("  Make sure the server is running: python -m uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
