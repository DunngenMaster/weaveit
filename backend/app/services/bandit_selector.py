"""
Bandit Policy Selector (Sprint 16.2)

Multi-armed bandit for learning which strategy works best per domain.
Uses UCB1 algorithm for exploration-exploitation balance.
"""

import math
from typing import Literal, Dict, Tuple, Optional
from app.services.redis_client import redis_client
from dashboard.publisher import dashboard


# Fixed strategy set (no runtime choices)
StrategyType = Literal[
    "S1_CLARIFY_FIRST",
    "S2_THREE_VARIANTS", 
    "S3_TEMPLATE_FIRST",
    "S4_STEPWISE"
]

STRATEGIES = [
    "S1_CLARIFY_FIRST",
    "S2_THREE_VARIANTS",
    "S3_TEMPLATE_FIRST",
    "S4_STEPWISE"
]

# Strategy instructions (hardcoded for Story 16.3)
STRATEGY_INSTRUCTIONS = {
    "S1_CLARIFY_FIRST": """STRATEGY: CLARIFY_FIRST
Before providing a solution, ask 2 clarifying questions to understand:
1. The user's specific context and constraints
2. Their preferred level of detail or format
Then provide a tailored answer based on their responses.""",

    "S2_THREE_VARIANTS": """STRATEGY: THREE_VARIANTS
Provide 3 distinct approaches to solve the problem:
- Option A: [Quick/simple approach]
- Option B: [Balanced approach]
- Option C: [Comprehensive approach]
End with a recommendation based on typical use cases.""",

    "S3_TEMPLATE_FIRST": """STRATEGY: TEMPLATE_FIRST
Start by providing a fill-in template or framework:
1. Give the template structure with clear placeholders
2. Provide a concrete example showing it filled out
3. Explain how to adapt it to their specific case""",

    "S4_STEPWISE": """STRATEGY: STEPWISE
Break the solution into clear, actionable steps:
1. [Step 1 with verification checkpoint]
2. [Step 2 with verification checkpoint]
3. [Step 3 with verification checkpoint]
Include how to verify each step succeeded before moving to the next."""
}


class BanditSelector:
    """
    Multi-armed bandit for strategy selection using UCB1 algorithm.
    
    Redis keys:
    - bandit:{user_id}:{domain}:{strategy}:shown (int)
    - bandit:{user_id}:{domain}:{strategy}:wins (int)
    TTL: 30 days (refreshed on each update)
    """
    
    def __init__(self):
        self.client = redis_client.client
        self.ttl_seconds = 30 * 24 * 60 * 60  # 30 days
    
    def _get_shown_key(self, user_id: str, domain: str, strategy: str) -> str:
        """Get Redis key for shown count"""
        return f"bandit:{user_id}:{domain}:{strategy}:shown"
    
    def _get_wins_key(self, user_id: str, domain: str, strategy: str) -> str:
        """Get Redis key for wins count"""
        return f"bandit:{user_id}:{domain}:{strategy}:wins"
    
    def get_stats(self, user_id: str, domain: str, strategy: str) -> Tuple[int, int]:
        """
        Get shown and wins counts for a strategy.
        
        Returns:
            Tuple of (shown_count, wins_count)
        """
        shown_key = self._get_shown_key(user_id, domain, strategy)
        wins_key = self._get_wins_key(user_id, domain, strategy)
        
        shown = int(self.client.get(shown_key) or 0)
        wins = int(self.client.get(wins_key) or 0)
        
        return shown, wins
    
    def _compute_ucb1_score(
        self,
        shown: int,
        wins: int,
        total_shown: int
    ) -> float:
        """
        Compute UCB1 score for a strategy.
        
        Formula: (wins/shown) + sqrt(2 * ln(total_shown) / shown)
        
        If shown==0, returns infinity (cold start - pick this first).
        
        Args:
            shown: Number of times this strategy was shown
            wins: Number of times this strategy won
            total_shown: Total shows across all strategies
            
        Returns:
            UCB1 score (higher is better)
        """
        if shown == 0:
            return float('inf')  # Cold start: try unexplored strategies first
        
        if total_shown <= 0:
            return 0.0
        
        exploitation = wins / shown
        exploration = math.sqrt(2 * math.log(total_shown) / shown)
        
        return exploitation + exploration
    
    def select_strategy(
        self,
        user_id: str,
        domain: str
    ) -> Tuple[str, Dict[str, float]]:
        """
        Select best strategy using UCB1 algorithm.
        
        Args:
            user_id: User identifier
            domain: Domain/category (resume, coding, etc)
            
        Returns:
            Tuple of (selected_strategy, all_scores_dict)
        """
        # Get stats for all strategies
        stats = {}
        total_shown = 0
        
        for strategy in STRATEGIES:
            shown, wins = self.get_stats(user_id, domain, strategy)
            stats[strategy] = {"shown": shown, "wins": wins}
            total_shown += shown
        
        # Compute UCB1 scores
        scores = {}
        for strategy in STRATEGIES:
            shown = stats[strategy]["shown"]
            wins = stats[strategy]["wins"]
            scores[strategy] = self._compute_ucb1_score(shown, wins, total_shown)
        
        # Select strategy with highest UCB1 score
        selected = max(scores, key=scores.get)
        
        print(f"[BANDIT] Selected {selected} for {domain} (scores: {scores})")
        
        # Publish to live dashboard
        dashboard.publish_sync("bandit_selection", {
            "strategy": selected,
            "domain": domain,
            "user_id": user_id,
            "ucb_scores": {k: round(v, 3) if v != float('inf') else 999.0 for k, v in scores.items()}
        })
        
        return selected, scores
    
    def record_shown(self, user_id: str, domain: str, strategy: str):
        """
        Increment shown count for a strategy.
        
        Called when strategy is presented to user.
        
        Args:
            user_id: User identifier
            domain: Domain/category
            strategy: Strategy that was shown
        """
        shown_key = self._get_shown_key(user_id, domain, strategy)
        
        self.client.incr(shown_key)
        self.client.expire(shown_key, self.ttl_seconds)
    
    def record_win(
        self,
        user_id: str,
        domain: str,
        strategy: str,
        outcome: str
    ):
        """
        Update bandit based on outcome.
        
        Called when attempt is resolved (success/fail).
        
        Args:
            user_id: User identifier
            domain: Domain/category
            strategy: Strategy that was used
            outcome: "success", "fail", or "unknown"
        """
        if outcome == "success":
            wins_key = self._get_wins_key(user_id, domain, strategy)
            new_wins = self.client.incr(wins_key)
            self.client.expire(wins_key, self.ttl_seconds)
            print(f"[BANDIT] Strategy {strategy} won for {domain}")
            
            # Publish to live dashboard
            dashboard.publish_sync("reward_update", {
                "strategy": strategy,
                "domain": domain,
                "user_id": user_id,
                "reward": 1,
                "total_rewards": new_wins,
                "outcome": outcome
            })
    
    def get_all_stats(self, user_id: str, domain: str) -> Dict[str, Dict[str, int]]:
        """
        Get stats for all strategies in a domain.
        
        Returns:
            Dict of {strategy: {shown, wins, win_rate}}
        """
        result = {}
        
        for strategy in STRATEGIES:
            shown, wins = self.get_stats(user_id, domain, strategy)
            win_rate = wins / shown if shown > 0 else 0.0
            result[strategy] = {
                "shown": shown,
                "wins": wins,
                "win_rate": round(win_rate, 3)
            }
        
        return result
    
    def get_instruction(self, strategy: str) -> str:
        """
        Get instruction block for a strategy.
        
        Used in Story 16.3 to inject into context.
        
        Args:
            strategy: Strategy name
            
        Returns:
            Instruction text for LLM
        """
        return STRATEGY_INSTRUCTIONS.get(strategy, "")


# Global instance
bandit_selector = BanditSelector()
