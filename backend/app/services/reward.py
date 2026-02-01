"""
Reward & Outcome Resolver: Deterministic evaluation of attempt success.

Infers whether the last attempt worked based on user's next message.
Backend-only, no frontend required.
"""

from typing import Literal
from datetime import datetime, timedelta
from pydantic import BaseModel


OutcomeType = Literal["success", "fail", "unknown"]


class RewardResult(BaseModel):
    """Result of reward computation."""
    reward: float
    outcome: OutcomeType
    reason: str


# Signal keywords for positive/negative outcomes
POSITIVE_SIGNALS = {
    "works", "worked", "perfect", "solved", "thanks", 
    "got it", "great", "awesome", "excellent", "good"
}

NEGATIVE_SIGNALS = {
    "not working", "still", "wrong", "no", "doesn't", 
    "didn't", "bad", "error", "failed", "issue"
}

NEXT_STEP_STARTERS = {
    "now", "next", "also", "ok", "great", "can you", 
    "could you", "please", "and", "then"
}


def compute_reward(
    new_message: str,
    new_fingerprint: str,
    previous_fingerprint: str | None,
    previous_timestamp_ms: int | None
) -> RewardResult:
    """
    Compute reward for the previous attempt based on new user message.
    
    This is called when a new USER_MESSAGE arrives, to evaluate the
    previous AI_RESPONSE in the same attempt thread.
    
    Args:
        new_message: The new user message text (lowercase for matching)
        new_fingerprint: Fingerprint of new message
        previous_fingerprint: Fingerprint of previous message (if exists)
        previous_timestamp_ms: Timestamp of previous message (if exists)
        
    Returns:
        RewardResult with reward score, outcome, and reason
        
    Rules (applied in order):
    1. Positive signals → +0.7, success
    2. Negative signals → -0.7, fail
    3. Repeat (same fingerprint within 10min) → -0.5, fail
    4. Next-step (different fingerprint, starts with trigger) → +0.5, success
    5. Default → 0.0, unknown
    """
    
    message_lower = new_message.lower()
    
    # Rule 1: Positive signals (highest priority)
    for signal in POSITIVE_SIGNALS:
        if signal in message_lower:
            return RewardResult(
                reward=0.7,
                outcome="success",
                reason=f"positive_signal:{signal}"
            )
    
    # Rule 2: Negative signals
    for signal in NEGATIVE_SIGNALS:
        if signal in message_lower:
            return RewardResult(
                reward=-0.7,
                outcome="fail",
                reason=f"negative_signal:{signal}"
            )
    
    # Rule 3: Repeat detection (same fingerprint within 10 minutes)
    if previous_fingerprint and new_fingerprint == previous_fingerprint:
        # Check if within 10 minutes
        if previous_timestamp_ms:
            time_diff_ms = datetime.now().timestamp() * 1000 - previous_timestamp_ms
            if time_diff_ms <= 10 * 60 * 1000:  # 10 minutes in milliseconds
                return RewardResult(
                    reward=-0.5,
                    outcome="fail",
                    reason="repeat_within_10min"
                )
    
    # Rule 4: Next-step detection (different fingerprint + starts with trigger)
    if previous_fingerprint and new_fingerprint != previous_fingerprint:
        # Check if message starts with next-step trigger
        for starter in NEXT_STEP_STARTERS:
            if message_lower.startswith(starter):
                return RewardResult(
                    reward=0.5,
                    outcome="success",
                    reason=f"next_step:{starter}"
                )
    
    # Rule 5: Default (no clear signal)
    return RewardResult(
        reward=0.0,
        outcome="unknown",
        reason="no_clear_signal"
    )


# Singleton function
reward_resolver = compute_reward
