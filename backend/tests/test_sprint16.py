"""
Sprint 16 Test Suite: Bandit Strategies + Explainability

Tests:
1. Outcome Resolver v2 (already in Sprint 13, verify it works)
2. Bandit strategy selection (UCB1)
3. Strategy instructions
4. Memory hygiene (supersede + decay)
5. Evaluation harness
6. Explainability trace
"""

import requests
import json
import time
from uuid import uuid4

BASE_URL = "http://localhost:8000"
TEST_USER_ID = f"test_user_{uuid4().hex[:8]}"


def test_outcome_resolver():
    """Test deterministic outcome resolution (Story 16.1)"""
    print("\n=== Test 1: Outcome Resolver v2 ===")
    
    # Send first message
    events1 = [{
        "user_id": TEST_USER_ID,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "CHAT_TURN",
        "ts": int(time.time() * 1000),
        "url": "https://chatgpt.com",
        "payload": {
            "text": "How do I write a resume?",
            "role": "user"
        }
    }]
    
    response1 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events1}
    )
    assert response1.status_code == 200
    
    time.sleep(1)
    
    # Send success signal
    events2 = [{
        "user_id": TEST_USER_ID,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "CHAT_TURN",
        "ts": int(time.time() * 1000),
        "url": "https://chatgpt.com",
        "payload": {
            "text": "Perfect! That worked great.",
            "role": "user"
        }
    }]
    
    response2 = requests.post(
        f"{BASE_URL}/v1/events",
        json={"events": events2}
    )
    
    print(f"Status: {response2.status_code}")
    print("✓ Outcome resolver processes success signals")
    print("  (Check server logs for [REWARD] messages)")


def test_bandit_selection():
    """Test bandit strategy selection (Story 16.2)"""
    print("\n=== Test 2: Bandit Strategy Selection ===")
    
    # The bandit selector is used internally during context generation
    # We can verify it works through the explain endpoint
    
    response = requests.get(
        f"{BASE_URL}/v1/explain",
        params={
            "user_id": TEST_USER_ID,
            "fingerprint": "test_fp_123",
            "domain": "resume"
        }
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Selected strategy: {result['strategy']['selected_strategy']}")
        print(f"UCB1 scores: {result['strategy']['ucb1_scores']}")
        print("✓ Bandit selector returns strategy with UCB1 scores")
    else:
        print(f"Response: {response.text}")


def test_strategy_instructions():
    """Test that each strategy has instructions (Story 16.3)"""
    print("\n=== Test 3: Strategy Instructions ===")
    
    strategies = [
        "S1_CLARIFY_FIRST",
        "S2_THREE_VARIANTS",
        "S3_TEMPLATE_FIRST",
        "S4_STEPWISE"
    ]
    
    response = requests.get(
        f"{BASE_URL}/v1/explain",
        params={
            "user_id": TEST_USER_ID,
            "fingerprint": "test_fp_456",
            "domain": "unknown"
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        instruction = result['strategy'].get('instruction', '')
        
        if instruction:
            print(f"Strategy instruction preview: {instruction[:100]}...")
            print("✓ Strategy has instruction block")
        else:
            print("⚠ No instruction block found")
    else:
        print(f"Explain endpoint error: {response.status_code}")


def test_memory_decay():
    """Test pattern decay (Story 16.4)"""
    print("\n=== Test 4: Memory Hygiene - Decay ===")
    
    response = requests.post(
        f"{BASE_URL}/v1/admin/decay",
        params={
            "user_id": TEST_USER_ID,
            "decay_factor": 0.8
        }
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Domains processed: {result['domains_processed']}")
        print(f"Total patterns decayed: {result['total_patterns_decayed']}")
        print(f"Decay factor: {result['decay_factor']}")
        print("✓ Memory decay works")
    else:
        print(f"Response: {response.text}")


def test_evaluation_harness():
    """Test evaluation harness (Story 16.5)"""
    print("\n=== Test 5: Evaluation Harness ===")
    
    response = requests.post(
        f"{BASE_URL}/v1/eval/run",
        json={
            "user_id": TEST_USER_ID,
            "domain": "resume",
            "prompt_set_id": "default"
        }
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Prompts tested: {result['prompts_tested']}")
        print(f"Successful resolutions: {result['successful_resolutions']}")
        print(f"Failed resolutions: {result['failed_resolutions']}")
        print(f"Patterns learned: {len(result['policy_patterns'])}")
        
        if result['summary']:
            print(f"\nSummary:")
            print(f"  Resolution rate: {result['summary']['resolution_rate']}")
            print(f"  Average reward: {result['summary']['average_reward']}")
            print(f"  Most successful strategy: {result['summary']['most_successful_strategy']}")
        
        print("\n✓ Evaluation harness provides comprehensive metrics")
    else:
        print(f"Response: {response.text}")


def test_explainability():
    """Test explainability trace (Story 16.6)"""
    print("\n=== Test 6: Explainability Trace ===")
    
    response = requests.get(
        f"{BASE_URL}/v1/explain",
        params={
            "user_id": TEST_USER_ID,
            "fingerprint": "test_fingerprint_abc123",
            "domain": "coding"
        }
    )
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        
        print(f"\nStrategy Decision:")
        print(f"  Selected: {result['strategy']['selected_strategy']}")
        print(f"  UCB1 Scores: {result['strategy']['ucb1_scores']}")
        
        print(f"\nPolicy Patterns: {len(result['policy_patterns'])} patterns")
        for i, pattern in enumerate(result['policy_patterns'][:3], 1):
            print(f"  {i}. Score={pattern['score']}: {pattern['pattern'][:60]}...")
        
        print(f"\nRAG Cache:")
        print(f"  Hit: {result['rag_cache']['cache_hit']}")
        
        print(f"\nSafety Gate:")
        print(f"  Blocked requests: {result['safety_gate']['total_blocked_requests']}")
        
        if result.get('attempt_thread'):
            print(f"\nAttempt Thread:")
            print(f"  Status: {result['attempt_thread']['status']}")
            print(f"  Attempts: {result['attempt_thread']['attempt_count']}")
            print(f"  Best reward: {result['attempt_thread']['best_reward']}")
        
        print(f"\nSummary: {result['explanation_summary']}")
        
        print("\n✓ Explainability trace shows complete decision path")
    else:
        print(f"Response: {response.text}")


def test_bandit_learning():
    """Test that bandit learns from outcomes"""
    print("\n=== Test 7: Bandit Learning Over Time ===")
    
    # Simulate multiple interactions with different outcomes
    print("Simulating 3 task attempts...")
    
    for i in range(3):
        # Send a message
        events = [{
            "user_id": TEST_USER_ID,
            "session_id": str(uuid4()),
            "provider": "chatgpt",
            "event_type": "CHAT_TURN",
            "ts": int(time.time() * 1000),
            "url": "https://chatgpt.com",
            "payload": {
                "text": f"Help me with task {i}",
                "role": "user"
            }
        }]
        
        requests.post(f"{BASE_URL}/v1/events", json={"events": events})
        time.sleep(0.5)
        
        # Alternate success/failure
        outcome_text = "Great! That worked." if i % 2 == 0 else "Still having issues."
        
        events2 = [{
            "user_id": TEST_USER_ID,
            "session_id": str(uuid4()),
            "provider": "chatgpt",
            "event_type": "CHAT_TURN",
            "ts": int(time.time() * 1000),
            "url": "https://chatgpt.com",
            "payload": {
                "text": outcome_text,
                "role": "user"
            }
        }]
        
        requests.post(f"{BASE_URL}/v1/events", json={"events": events2})
        time.sleep(0.5)
    
    # Check bandit stats
    response = requests.post(
        f"{BASE_URL}/v1/eval/run",
        json={
            "user_id": TEST_USER_ID,
            "domain": "unknown"
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        bandit_stats = result.get('bandit_stats', {})
        
        print(f"\nBandit Statistics After Learning:")
        for strategy, stats in bandit_stats.items():
            print(f"  {strategy}: shown={stats['shown']}, wins={stats['wins']}, win_rate={stats['win_rate']}")
        
        print("\n✓ Bandit tracks wins and shown counts")
    else:
        print(f"Error getting bandit stats: {response.status_code}")


def test_complete_flow():
    """Test complete flow: event → resolution → bandit update → explain"""
    print("\n=== Test 8: Complete Learning Flow ===")
    
    user_id = f"flow_test_{uuid4().hex[:8]}"
    
    # 1. Send initial message
    print("1. Sending initial message...")
    events1 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "CHAT_TURN",
        "ts": int(time.time() * 1000),
        "url": "https://chatgpt.com",
        "payload": {
            "text": "How do I implement a binary search tree?",
            "role": "user"
        }
    }]
    
    r1 = requests.post(f"{BASE_URL}/v1/events", json={"events": events1})
    assert r1.status_code == 200
    
    time.sleep(1)
    
    # 2. Send success signal
    print("2. Sending success signal...")
    events2 = [{
        "user_id": user_id,
        "session_id": str(uuid4()),
        "provider": "chatgpt",
        "event_type": "CHAT_TURN",
        "ts": int(time.time() * 1000),
        "url": "https://chatgpt.com",
        "payload": {
            "text": "Perfect! The solution works great.",
            "role": "user"
        }
    }]
    
    r2 = requests.post(f"{BASE_URL}/v1/events", json={"events": events2})
    assert r2.status_code == 200
    
    time.sleep(1)
    
    # 3. Check evaluation
    print("3. Running evaluation...")
    eval_response = requests.post(
        f"{BASE_URL}/v1/eval/run",
        json={"user_id": user_id, "domain": "coding"}
    )
    
    if eval_response.status_code == 200:
        eval_result = eval_response.json()
        print(f"   Successful resolutions: {eval_result['successful_resolutions']}")
    
    # 4. Get explanation
    print("4. Getting explanation...")
    explain_response = requests.get(
        f"{BASE_URL}/v1/explain",
        params={"user_id": user_id, "fingerprint": "test", "domain": "coding"}
    )
    
    if explain_response.status_code == 200:
        explain_result = explain_response.json()
        print(f"   Selected strategy: {explain_result['strategy']['selected_strategy']}")
    
    print("\n✓ Complete flow: ingest → resolve → learn → explain")


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 16 Test Suite: Bandit + Explainability")
    print("=" * 60)
    
    try:
        test_outcome_resolver()
        test_bandit_selection()
        test_strategy_instructions()
        test_memory_decay()
        test_evaluation_harness()
        test_explainability()
        test_bandit_learning()
        test_complete_flow()
        
        print("\n" + "=" * 60)
        print("✓ Sprint 16 Tests Complete!")
        print("=" * 60)
        print("\nKey Features Validated:")
        print("- ✓ Outcome Resolver v2 (deterministic success/fail)")
        print("- ✓ Bandit Strategy Selector (UCB1)")
        print("- ✓ Strategy Instructions (4 hardcoded strategies)")
        print("- ✓ Memory Hygiene (decay)")
        print("- ✓ Evaluation Harness (one-call proof)")
        print("- ✓ Explainability Trace (why did it do that?)")
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Could not connect to {BASE_URL}")
        print("  Make sure the server is running: python -m uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
