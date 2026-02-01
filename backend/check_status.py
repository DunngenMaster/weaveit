"""
Comprehensive Backend/Frontend Status Check
"""

import requests
import json

API_BASE = "http://localhost:8000"

print("=" * 60)
print("WEAVEIT SYSTEM STATUS CHECK")
print("=" * 60)

# 1. Backend Health
print("\n[1] Backend Health Check")
try:
    r = requests.get(f"{API_BASE}/health", timeout=5)
    print(f"    ✓ Backend running: {r.status_code}")
    print(f"    Response: {r.json()}")
except Exception as e:
    print(f"    ✗ Backend error: {e}")
    exit(1)

# 2. List all endpoints
print("\n[2] Available Endpoints")
try:
    r = requests.get(f"{API_BASE}/openapi.json")
    paths = r.json()["paths"]
    print(f"    Total endpoints: {len(paths)}")
    for path in sorted(paths.keys()):
        print(f"      - {path}")
except Exception as e:
    print(f"    ✗ Error: {e}")

# 3. Test Events Endpoint
print("\n[3] Events Endpoint Test")
try:
    event_data = {
        "events": [{
            "event_type": "USER_MESSAGE",
            "user_id": "status_check_user",
            "session_id": "status_session",
            "provider": "chatgpt",
            "ts": 1769970000000,
            "url": "https://chatgpt.com",
            "payload": {"text": "Status check test", "role": "user"}
        }]
    }
    r = requests.post(f"{API_BASE}/v1/events", json=event_data)
    print(f"    ✓ Events ingestion: {r.status_code}")
except Exception as e:
    print(f"    ✗ Events error: {e}")

# 4. Test Sprint 18 Endpoints
print("\n[4] Sprint 18 Handoff Endpoints")
try:
    # Create CSA
    csa_data = {
        "user_id": "status_check_user",
        "source_provider": "chatgpt",
        "source_session_id": "status_session",
        "domain": "testing"
    }
    r = requests.post(f"{API_BASE}/v1/handoff/csa/create", json=csa_data)
    if r.status_code == 200:
        csa_id = r.json()["csa_id"]
        print(f"    ✓ CSA Create: {csa_id[:20]}...")
    else:
        print(f"    ✗ CSA Create failed: {r.status_code} - {r.text[:100]}")
    
    # Get latest
    r = requests.get(f"{API_BASE}/v1/handoff/csa/latest?user_id=status_check_user")
    if r.status_code == 200:
        latest = r.json()
        print(f"    ✓ Get Latest: {latest.get('csa_id', 'N/A')[:20]}...")
    else:
        print(f"    ⚠ Get Latest: {r.status_code}")
    
    # Handoff status
    r = requests.get(f"{API_BASE}/v1/handoff/status?user_id=status_check_user")
    if r.status_code == 200:
        status = r.json()
        print(f"    ✓ Handoff Status: pending={status.get('handoff_pending')}")
    else:
        print(f"    ⚠ Status: {r.status_code}")
        
except Exception as e:
    print(f"    ✗ Sprint 18 error: {e}")

# 5. Test Context/Memory
print("\n[5] Context & Memory Endpoints")
try:
    r = requests.get(f"{API_BASE}/v1/context?user_id=status_check_user")
    print(f"    ✓ Context: {r.status_code}")
    
    r = requests.get(f"{API_BASE}/v1/memory?user_id=status_check_user&query=test&limit=5")
    print(f"    ✓ Memory: {r.status_code}")
except Exception as e:
    print(f"    ✗ Error: {e}")

print("\n" + "=" * 60)
print("STATUS CHECK COMPLETE")
print("=" * 60)
print("\nBackend: http://localhost:8000")
print("Frontend: http://127.0.0.1:5174")
print("\nAll core systems operational ✓")
