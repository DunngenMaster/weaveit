# WeavelT Self-Improvement System - Complete Flow

## How Self-Improvement Actually Works (Based on Real User Activity)

### 1. USER ACTIVITY TRIGGERS LEARNING

When you browse and interact, events flow like this:

```
USER BROWSER → Frontend → POST /v1/events → Backend Processing → Learning Happens
```

### 2. EVENT FLOW (events.py)

**Every user message goes through:**

1. **Normalization** → Convert raw events to canonical format
2. **Safety Check** → Gemini moderation (safety_gate.py)
3. **Fingerprint** → Hash message to detect repeats
4. **Attempt Thread** → Track related attempts at same problem
5. **Handoff Detection** → Check if CSA needed
6. **Critic Scoring** → AI responses get quality scores (0-1)
7. **Reward Calculation** → Based on next user message:
   - "works!" / "perfect" → +0.7 (success)
   - "still broken" / "error" → -0.7 (fail)
   - Repeat within 10min → -0.5 (fail)
   - New topic → +0.5 (success)

### 3. BANDIT LEARNING (bandit_selector.py)

**UCB1 Algorithm selects strategies:**

- Tries unexplored strategies first (cold start)
- Balances exploration vs exploitation
- Higher UCB score = more likely to select
- Formula: `(wins/shown) + sqrt(2 * ln(total_shown) / shown)`

**4 Strategies:**
- S1_CLARIFY_FIRST - Ask questions before answering
- S2_THREE_VARIANTS - Give 3 options
- S3_TEMPLATE_FIRST - Start with template
- S4_STEPWISE - Step-by-step instructions

**Learning happens when:**
```python
# Selection (eval.py or context building)
strategy, scores = bandit_selector.select_strategy(user_id, domain)
bandit_selector.record_shown(user_id, domain, strategy)

# Reward (events.py after user responds)
reward_result = reward_resolver(new_message, fingerprint, prev_fingerprint, prev_ts)
bandit_selector.record_win(user_id, domain, strategy, outcome)
```

### 4. POLICY LEARNING (policy_manager.py)

**Successful patterns get stored:**

```python
# After critic scores response well + user gives positive signal
score = reward * critic_score
policy_manager.add_pattern(user_id, domain, pattern, reward, critic_score)
```

**Best patterns injected into future context:**
```python
patterns = policy_manager.get_top_patterns(user_id, domain, limit=3)
# These get added to context for next AI response
```

### 5. WHERE BANDIT SELECTION HAPPENS

**Currently used in:**

1. **eval.py** - `/v1/eval/run` endpoint
   - Runs evaluation harness
   - Tests 5 fixed prompts
   - Shows learning metrics

2. **eval.py** - `/v1/eval/explain` endpoint  
   - Explainability trace
   - Shows why strategy was selected

**NOT currently used in:**
- Main `/v1/events` flow (should be!)
- `/v1/context` building (should be!)

### 6. COMPLETE USER JOURNEY

```
1. User searches for "software engineer jobs" in browser
   → Frontend captures via extension
   → POST /v1/events with USER_MESSAGE

2. Backend processes:
   → Fingerprint: "abc123..."
   → Attempt thread created/updated
   → Safety check: PASS
   → Handoff check: Not needed yet

3. AI responds with job search advice
   → POST /v1/events with AI_RESPONSE
   → Critic scores response: 0.85 (good)
   → Stored with attempt record

4. User says "perfect, found 3 jobs!"
   → POST /v1/events with USER_MESSAGE
   → Reward calculator sees "perfect" → +0.7
   → Updates previous attempt: reward=0.7, outcome="success"
   → If this attempt was best: becomes template for future

5. Next time user has similar task:
   → Context retrieves top policy patterns
   → Bandit selects strategy based on past wins
   → System is smarter!
```

### 7. WHAT'S MISSING FOR DASHBOARD

**To show self-improvement on dashboard in real-time:**

Need to add bandit selection to the MAIN flow:

```python
# In events.py when USER_MESSAGE arrives:
if canonical.event_type == "USER_MESSAGE":
    # ADDED: Select strategy using bandit
    domain = classify_domain(text)  # resume/coding/job_search/writing
    strategy, ucb_scores = bandit_selector.select_strategy(user_id, domain)
    bandit_selector.record_shown(user_id, domain, strategy)
    
    # Store selected strategy in payload
    canonical.payload["selected_strategy"] = strategy
    canonical.payload["domain"] = domain
    
    # Publish to dashboard
    dashboard.publish_sync("bandit_selection", {
        "strategy": strategy,
        "domain": domain,
        "user_id": user_id,
        "ucb_scores": ucb_scores
    })
```

### 8. CURRENT STATE

✅ **Working:**
- Event ingestion
- Critic scoring
- Reward calculation
- Attempt tracking
- Policy learning
- Bandit algorithm

⚠️ **Not Integrated:**
- Bandit selection in main event flow
- Strategy injection into AI responses
- Real-time dashboard updates from actual usage
- Domain classification from user messages

🎯 **Dashboard shows learning when:**
- Run `/v1/eval/run` endpoint (test harness)
- Run demo script (simulated learning)

📊 **Dashboard SHOULD show learning when:**
- Real user browses and interacts
- Events flow through `/v1/events`
- Strategies selected and rewarded based on actual outcomes

### 9. THE FIX NEEDED

To make self-improvement visible during real browsing:

1. Add domain classifier (resume/coding/job_search/writing)
2. Integrate bandit selection into events.py
3. Record shown/win in events flow
4. Publish events to dashboard
5. Inject selected strategy into context for AI

Then the dashboard will update live as you browse and interact!
