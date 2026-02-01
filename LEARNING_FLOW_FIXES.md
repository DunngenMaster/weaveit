# Learning Flow Fixes

## Problem Description
The learning feedback loop was broken. When users submitted feedback to improve results, the system appeared to change results but was NOT actually learning or retaining those improvements for future runs.

## Root Cause Analysis

### Bug #1: Empty Patch in RunMemory
**Location:** `backend/app/agent/orchestrator.py:147`

**Issue:** When a run completed, it wrote to Weaviate RunMemory with an empty patch `{}` instead of the actual learned patch from Redis:
```python
# BEFORE (broken)
_write_run_memory(run_id, goal, query, summary, policy or {}, prompt_delta or {}, {}, metrics)
```

**Impact:** Any patches generated from user feedback were discarded when the run completed.

---

### Bug #2: Loading Wrong Data from Weaviate
**Location:** `backend/app/api/routes/runs.py:71-81`

**Issue:** When retrieving learned policies from Weaviate for new runs, the code was loading from `policy_json` (original policy) instead of `patch_json` (learned changes):
```python
# BEFORE (broken)
policy_from_mem = json.loads(policy_json)  # Original policy, not learned changes!
for key, value in policy_from_mem.items():
    if key in policy and value is not None:
        policy[key] = str(value)
```

**Impact:** Even if patches were stored correctly, they were never applied to new runs.

---

### Bug #3: Feedback Patch Overwritten
**Location:** `backend/app/api/routes/feedback.py:80` + `backend/app/agent/orchestrator.py:147`

**Issue:** The system created TWO RunMemory entries for each run:
1. When feedback was submitted → RunMemory with patch ✅
2. When run completed → NEW RunMemory with empty patch, overwriting #1 ❌

**Impact:** Feedback patches were written but immediately overwritten.

---

## Fixes Applied

### Fix #1: Retrieve and Pass Actual Patch
**File:** `backend/app/agent/orchestrator.py`

```python
# AFTER (fixed)
# Retrieve patch if feedback was submitted
patch_from_redis = {}
patch_key = f"run:{run_id}:patch"
patch_data = client.hgetall(patch_key) or {}
if patch_data.get("patch"):
    try:
        patch_from_redis = json.loads(patch_data.get("patch", "{}"))
    except Exception:
        pass

_write_run_memory(run_id, goal, query, summary, policy or {}, prompt_delta or {}, patch_from_redis, metrics)
```

**Result:** Learned patches are now persisted to Weaviate.

---

### Fix #2: Load Learned Patches from Weaviate
**File:** `backend/app/api/routes/runs.py`

```python
# AFTER (fixed)
if memories:
    mem = memories[0]
    # Load learned patch if it exists
    patch_json = mem.get("patch_json") or "{}"
    prompt_json = mem.get("prompt_delta_json") or "{}"
    learned_patch = json.loads(patch_json)
    prompt_delta = json.loads(prompt_json)
    
    # Apply policy_delta from the learned patch
    policy_delta = learned_patch.get("policy_delta", {}) or {}
    for key, value in policy_delta.items():
        if key in policy and value is not None:
            policy[key] = str(value)
    
    # Also merge prompt_delta from patch if exists
    patch_prompt_delta = learned_patch.get("prompt_delta", {}) or {}
    prompt_delta.update(patch_prompt_delta)
```

**Result:** New runs now load and apply learned policy changes.

---

### Fix #3: Don't Overwrite Feedback Patches
**File:** `backend/app/agent/orchestrator.py`

```python
# AFTER (fixed)
def _write_run_memory(run_id: str, goal: str, query: str, summary: dict, policy: dict, prompt_delta: dict, patch: dict, metrics: dict):
    # Check if a RunMemory with this run_id already exists (from feedback)
    # If it does and has a patch, don't overwrite it
    try:
        existing = collection.query.fetch_objects(
            filters=wvc.query.Filter.by_property("run_id").equal(run_id),
            limit=1
        )
        if existing.objects and existing.objects[0].properties.get("patch_json"):
            existing_patch = json.loads(existing.objects[0].properties.get("patch_json", "{}"))
            if existing_patch.get("policy_delta") or existing_patch.get("prompt_delta"):
                print(f"[RunMemory] Skipping write for {run_id} - already has feedback patch")
                return True
    except Exception as check_error:
        print(f"[RunMemory] Error checking existing: {check_error}")
    
    # Only write if no existing patch
    collection.data.insert({...})
```

**Result:** Feedback-generated patches are preserved and not overwritten.

---

## Complete Learning Flow (Fixed)

### Step 1: User Starts Search
1. Frontend calls `POST /runs`
2. Backend checks Redis for `tab:{tab_id}:patch` (24-hour memory)
3. If no Redis patch, queries Weaviate `RunMemory` for similar goals
4. Loads `patch_json` from best matching memory
5. Applies `policy_delta` to default policy
6. Starts agent run with learned policy

### Step 2: Agent Executes
1. Agent runs with learned policy parameters
2. Saves results to Redis `run:{run_id}`
3. At completion, checks for existing feedback patch
4. If no feedback patch exists, writes RunMemory with empty patch (baseline)

### Step 3: User Submits Feedback
1. Frontend calls `POST /feedback` with tags/notes
2. Backend generates patch using Gemini LLM:
   - Analyzes execution trace
   - Compares to user feedback
   - Generates `policy_delta` (e.g., `{"max_tabs": 15, "min_score": 0.7}`)
3. Saves patch to:
   - Redis `run:{run_id}:patch` (for this specific run)
   - Redis `tab:{tab_id}:patch` (for this tab, 24h TTL)
   - Weaviate `RunMemory` (permanent, searchable)

### Step 4: Next Search in Same Tab (Within 24h)
1. User starts new search in same tab
2. Backend finds `tab:{tab_id}:patch` in Redis
3. Applies learned policy immediately (hot cache)
4. Agent runs with improved parameters

### Step 5: Next Search in New Tab or After 24h
1. User starts search in different tab or after Redis expiry
2. No Redis patch found
3. Backend queries Weaviate RunMemory with BM25 semantic search
4. Finds similar goal from history
5. Loads `patch_json` from best match
6. Applies learned policy
7. Agent benefits from past learning

---

## Testing the Fix

### Test Case 1: Learning Within Same Tab
```bash
# 1. Start first search
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "find noise-cancelling headphones", "query": "best ANC headphones 2026", "limit": 5, "tab_id": "test-tab-1"}'

# 2. Submit feedback (too many results)
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{"run_id": "<run_id>", "tab_id": "test-tab-1", "tags": ["too_many_results"], "notes": "Only show top 3"}'

# 3. Start second search (should use fewer tabs)
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "find noise-cancelling headphones", "query": "ANC headphones under $300", "limit": 5, "tab_id": "test-tab-1"}'

# Verify: Check run policy has reduced max_tabs
```

### Test Case 2: Learning Across Different Tabs
```bash
# 1. Do search + feedback in tab-1 (as above)

# 2. Start search in NEW tab with similar goal
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"goal": "find wireless headphones", "query": "best wireless headphones", "limit": 5, "tab_id": "test-tab-2"}'

# Verify: Weaviate semantic search should find similar goal and apply learned patch
```

### Test Case 3: Verify Dashboard Shows Learning
1. Open Streamlit dashboard: http://localhost:8501
2. Run tests above
3. Check "Learning Patches" section shows generated patches
4. Check "Policy Evolution" charts show changes over time
5. Verify Weaviate Collections count increases

---

## Key Improvements

✅ **Feedback is now persistent** - Patches saved to Weaviate long-term memory  
✅ **Learning transfers across tabs** - BM25 semantic search finds similar goals  
✅ **Fast learning within tab** - Redis cache applies patches immediately (24h)  
✅ **Prevents overwrites** - Feedback patches protected from run completion  
✅ **Proper data flow** - patch_json used instead of policy_json  
✅ **Visible in dashboard** - Real-time visualization of learning progression  

---

## Files Modified
- `backend/app/agent/orchestrator.py` - Retrieve patch, prevent overwrites
- `backend/app/api/routes/runs.py` - Load from patch_json, apply policy_delta
- `backend/dashboard/dashboard_streamlit.py` - Clean UI, visualization improvements

## Next Steps
1. Test end-to-end learning flow with real searches
2. Monitor dashboard for patch generation and application
3. Verify Weaviate RunMemory growth over time
4. Consider adding patch quality scoring based on results
