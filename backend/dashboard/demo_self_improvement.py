"""
Self-Improvement Demo - Shows the AI learning in real-time

This simulates the multi-armed bandit learning which strategy works best.
Watch the dashboard at http://localhost:8001 to see:
1. Strategies being selected based on UCB scores
2. Rewards given (positive/negative)
3. UCB scores updating as the system learns
4. Better strategies getting selected more often over time
"""

import asyncio
import random
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from dashboard.publisher import dashboard
from app.services.bandit_selector import bandit_selector


# Simulate different domains with different "true" best strategies
DOMAIN_TRUTH = {
    "resume": "S1_CLARIFY_FIRST",      # Asking questions works best for resumes
    "coding": "S4_STEPWISE",            # Step-by-step works best for coding
    "job_search": "S2_THREE_VARIANTS",  # Giving options works best for job search
    "writing": "S3_TEMPLATE_FIRST"      # Templates work best for writing
}

# Strategy success probabilities (if it's the "right" strategy vs "wrong" strategy)
RIGHT_STRATEGY_SUCCESS = 0.85  # 85% success rate for optimal strategy
WRONG_STRATEGY_SUCCESS = 0.45  # 45% success rate for suboptimal strategy


async def simulate_learning_loop():
    """
    Simulate the AI learning which strategy works best for each domain.
    
    The system starts with no knowledge, explores all strategies,
    then gradually converges on the best strategy for each domain.
    """
    
    user_id = "demo_user_001"
    iteration = 0
    
    print("🤖 SELF-IMPROVEMENT DEMO STARTING")
    print("=" * 60)
    print(f"📊 Open http://localhost:8001 to watch the AI learn in real-time!")
    print("")
    print("The system will:")
    print("  1. Try different strategies for different tasks")
    print("  2. Get rewards (positive/negative) based on success")
    print("  3. Update its UCB scores to prefer winning strategies")
    print("  4. Gradually improve its strategy selection")
    print("")
    print("Watch the dashboard to see UCB scores change and")
    print("better strategies get selected more often over time!")
    print("=" * 60)
    print("")
    
    # Run learning loop
    while iteration < 100:
        iteration += 1
        
        # Pick random domain
        domain = random.choice(list(DOMAIN_TRUTH.keys()))
        true_best_strategy = DOMAIN_TRUTH[domain]
        
        # Let bandit select strategy using UCB1
        selected_strategy, ucb_scores = bandit_selector.select_strategy(user_id, domain)
        
        # Record that we showed this strategy
        bandit_selector.record_shown(user_id, domain, selected_strategy)
        
        # Publish selection to dashboard
        await dashboard.publish("bandit_selection", {
            "strategy": selected_strategy,
            "domain": domain,
            "user_id": user_id,
            "iteration": iteration,
            "ucb_scores": {k: round(v, 3) if v != float('inf') else 999.0 for k, v in ucb_scores.items()}
        })
        
        print(f"[{iteration:3d}] {domain:12s} → Selected: {selected_strategy:20s}", end="")
        
        # Simulate outcome based on whether we picked the right strategy
        if selected_strategy == true_best_strategy:
            # Right strategy: high success probability
            success = random.random() < RIGHT_STRATEGY_SUCCESS
        else:
            # Wrong strategy: low success probability
            success = random.random() < WRONG_STRATEGY_SUCCESS
        
        # Determine outcome and reward
        if success:
            outcome = "success"
            reward = 0.7
            print(f" ✅ SUCCESS (+{reward})")
        else:
            outcome = "fail"
            reward = -0.5
            print(f" ❌ FAIL ({reward})")
        
        # Record win/fail with bandit
        bandit_selector.record_win(user_id, domain, selected_strategy, outcome)
        
        # Get updated stats
        stats = bandit_selector.get_all_stats(user_id, domain)
        
        # Publish reward to dashboard
        total_wins = stats[selected_strategy]["wins"]
        await dashboard.publish("reward_update", {
            "strategy": selected_strategy,
            "domain": domain,
            "user_id": user_id,
            "reward": reward,
            "total_rewards": total_wins,
            "outcome": outcome,
            "iteration": iteration
        })
        
        # Simulate judge scoring the response quality
        if success:
            judge_score = random.uniform(0.75, 0.95)
            violations = []
        else:
            judge_score = random.uniform(0.30, 0.65)
            violations = random.choice([
                ["NOT_SPECIFIC"],
                ["TOO_LONG"],
                ["MISALIGNED"],
                []
            ])
        
        await dashboard.publish("judge_evaluation", {
            "score": round(judge_score, 2),
            "violations": violations,
            "reasons": ["Automated evaluation"],
            "criteria": "quality_compliance",
            "domain": domain,
            "iteration": iteration
        })
        
        # Every 10 iterations, show learning progress
        if iteration % 10 == 0:
            print("")
            print(f"📈 LEARNING PROGRESS after {iteration} attempts:")
            for dom, best_strat in DOMAIN_TRUTH.items():
                dom_stats = bandit_selector.get_all_stats(user_id, dom)
                best_shown = dom_stats[best_strat]["shown"]
                best_wins = dom_stats[best_strat]["wins"]
                best_rate = dom_stats[best_strat]["win_rate"]
                
                total_shown = sum(s["shown"] for s in dom_stats.values())
                if total_shown > 0:
                    selection_rate = (best_shown / total_shown) * 100
                    print(f"  {dom:12s}: Optimal strategy selected {selection_rate:5.1f}% of time (win rate: {best_rate:.1%})")
            print("")
        
        # Wait between iterations (faster at first for exploration, slower as it learns)
        wait_time = 0.3 if iteration < 20 else 0.5
        await asyncio.sleep(wait_time)
    
    print("")
    print("=" * 60)
    print("🎉 LEARNING COMPLETE!")
    print("")
    print("Final Results - How often the AI picked the BEST strategy:")
    print("")
    
    for domain, best_strategy in DOMAIN_TRUTH.items():
        stats = bandit_selector.get_all_stats(user_id, domain)
        best_shown = stats[best_strategy]["shown"]
        best_wins = stats[best_strategy]["wins"]
        best_rate = stats[best_strategy]["win_rate"]
        
        total_shown = sum(s["shown"] for s in stats.values())
        selection_rate = (best_shown / total_shown) * 100 if total_shown > 0 else 0
        
        print(f"  {domain:12s}: {selection_rate:5.1f}% → Best: {best_strategy}")
        print(f"                Win rate: {best_rate:.1%} ({best_wins}/{best_shown} attempts)")
        print("")
    
    print("The AI has learned which strategies work best for each task!")
    print("Check the dashboard to see the final UCB scores and performance chart.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(simulate_learning_loop())
