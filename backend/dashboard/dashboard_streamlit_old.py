"""
🚀 WeaveIt Real-Time Self-Learning Dashboard

Shows:
- Active agent runs in real-time
- Learning progression (policies evolving)
- Redis data flow (what's stored, how it changes)
- Weaviate knowledge growth
- Feedback → Learning → Improvement cycle

Run: streamlit run dashboard_streamlit.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
import json
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client

# ============= PAGE CONFIG =============
st.set_page_config(
    page_title="WeaveIt Learning Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============= LIGHT THEME CSS =============
st.markdown("""
<style>
    /* Main background */
    .main {
        background: linear-gradient(135deg, #f5f7fa 0%, #e3e9f0 100%);
    }
    
    /* Metric cards */
    .stMetric {
        background: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid #3b82f6;
    }
    
    /* Headers */
    h1 {
        color: #1e293b;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    
    h2, h3 {
        color: #334155;
        font-weight: 600;
    }
    
    /* Cards */
    .status-card {
        background: white;
        padding: 16px;
        border-radius: 10px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        margin-bottom: 12px;
        border-left: 3px solid;
    }
    
    .running {
        border-left-color: #10b981;
    }
    
    .completed {
        border-left-color: #3b82f6;
    }
    
    .learning {
        border-left-color: #f59e0b;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #ffffff;
    }
    
    /* Info boxes */
    .stAlert {
        background-color: #f0f9ff;
        border-left: 4px solid #3b82f6;
    }
    
    /* Tables */
    .dataframe {
        background-color: white;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.title("🤖 WeavelT Self-Improvement Dashboard")
st.markdown("### Real-time Multi-Armed Bandit Learning")

# Sidebar controls
st.sidebar.header("⚙️ Controls")
user_id = st.sidebar.text_input("User ID", value="demo_user_001")
auto_refresh = st.sidebar.checkbox("Auto-refresh (every 2s)", value=True)
show_raw_data = st.sidebar.checkbox("Show Raw Data", value=False)

# Domain truth (what the AI should learn)
DOMAIN_TRUTH = {
    "resume": "S1_CLARIFY_FIRST",
    "coding": "S4_STEPWISE",
    "job_search": "S2_THREE_VARIANTS",
    "writing": "S3_TEMPLATE_FIRST"
}

st.sidebar.markdown("---")
st.sidebar.markdown("### 📚 Domain Truth")
st.sidebar.markdown("What strategies **should** work best:")
for domain, strategy in DOMAIN_TRUTH.items():
    st.sidebar.markdown(f"**{domain}**: `{strategy}`")


def get_bandit_stats(user_id: str, domain: str):
    """Get bandit statistics for a domain"""
    try:
        stats = bandit_selector.get_all_stats(user_id, domain)
        return stats
    except:
        return {}


def calculate_learning_progress(user_id: str):
    """Calculate how well the AI has learned"""
    progress = {}
    
    for domain, true_best in DOMAIN_TRUTH.items():
        stats = get_bandit_stats(user_id, domain)
        
        if not stats:
            progress[domain] = {
                "optimal_selection_rate": 0,
                "optimal_win_rate": 0,
                "total_attempts": 0
            }
            continue
        
        total_shown = sum(s["shown"] for s in stats.values())
        best_shown = stats.get(true_best, {}).get("shown", 0)
        best_wins = stats.get(true_best, {}).get("wins", 0)
        best_win_rate = stats.get(true_best, {}).get("win_rate", 0)
        
        selection_rate = (best_shown / total_shown * 100) if total_shown > 0 else 0
        
        progress[domain] = {
            "optimal_selection_rate": selection_rate,
            "optimal_win_rate": best_win_rate * 100,
            "total_attempts": total_shown,
            "optimal_attempts": best_shown,
            "optimal_wins": best_wins
        }
    
    return progress


# Main dashboard
col1, col2, col3, col4 = st.columns(4)

# Overall metrics
progress = calculate_learning_progress(user_id)
total_attempts = sum(p["total_attempts"] for p in progress.values())
avg_optimal_rate = sum(p["optimal_selection_rate"] for p in progress.values()) / len(progress) if progress else 0
avg_win_rate = sum(p["optimal_win_rate"] for p in progress.values()) / len(progress) if progress else 0

with col1:
    st.metric("Total Attempts", total_attempts)

with col2:
    st.metric("Avg Optimal Selection", f"{avg_optimal_rate:.1f}%")

with col3:
    st.metric("Avg Win Rate", f"{avg_win_rate:.1f}%")

with col4:
    st.metric("Domains", len(DOMAIN_TRUTH))

st.markdown("---")

# Learning progress by domain
st.subheader("📊 Learning Progress by Domain")

col1, col2 = st.columns(2)

with col1:
    # Optimal selection rate chart
    fig_selection = go.Figure()
    
    domains = list(progress.keys())
    selection_rates = [progress[d]["optimal_selection_rate"] for d in domains]
    
    fig_selection.add_trace(go.Bar(
        x=domains,
        y=selection_rates,
        marker_color=['#10b981', '#f59e0b', '#3b82f6', '#8b5cf6'],
        text=[f"{r:.1f}%" for r in selection_rates],
        textposition='auto',
    ))
    
    fig_selection.update_layout(
        title="How Often AI Picks Optimal Strategy",
        yaxis_title="Selection Rate (%)",
        yaxis_range=[0, 100],
        height=400,
        template="plotly_dark"
    )
    
    st.plotly_chart(fig_selection, use_container_width=True)

with col2:
    # Win rate chart
    fig_winrate = go.Figure()
    
    win_rates = [progress[d]["optimal_win_rate"] for d in domains]
    
    fig_winrate.add_trace(go.Bar(
        x=domains,
        y=win_rates,
        marker_color=['#10b981', '#f59e0b', '#3b82f6', '#8b5cf6'],
        text=[f"{r:.1f}%" for r in win_rates],
        textposition='auto',
    ))
    
    fig_winrate.update_layout(
        title="Win Rate for Optimal Strategy",
        yaxis_title="Win Rate (%)",
        yaxis_range=[0, 100],
        height=400,
        template="plotly_dark"
    )
    
    st.plotly_chart(fig_winrate, use_container_width=True)

# UCB Scores visualization
st.subheader("🎯 Current UCB Scores (Exploration vs Exploitation)")

tabs = st.tabs(list(DOMAIN_TRUTH.keys()))

for idx, domain in enumerate(DOMAIN_TRUTH.keys()):
    with tabs[idx]:
        stats = get_bandit_stats(user_id, domain)
        
        if not stats:
            st.info(f"No data yet for {domain}")
            continue
        
        # Calculate current UCB scores
        strategies = list(stats.keys())
        shown_counts = [stats[s]["shown"] for s in strategies]
        win_counts = [stats[s]["wins"] for s in strategies]
        win_rates = [stats[s]["win_rate"] for s in strategies]
        
        # Create dataframe
        df = pd.DataFrame({
            "Strategy": strategies,
            "Shown": shown_counts,
            "Wins": win_counts,
            "Win Rate": [f"{r:.1%}" for r in win_rates],
            "Win Rate (%)": [r * 100 for r in win_rates]
        })
        
        # Highlight optimal strategy
        optimal = DOMAIN_TRUTH[domain]
        df["Is Optimal"] = df["Strategy"] == optimal
        
        # Bar chart
        fig = px.bar(
            df,
            x="Strategy",
            y="Win Rate (%)",
            color="Is Optimal",
            color_discrete_map={True: "#10b981", False: "#6b7280"},
            text="Win Rate",
            title=f"{domain.title()} - Strategy Performance"
        )
        
        fig.update_layout(
            height=300,
            template="plotly_dark",
            showlegend=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Show table
        if show_raw_data:
            st.dataframe(df, use_container_width=True)

# Learning insights
st.markdown("---")
st.subheader("💡 Learning Insights")

insights_col1, insights_col2 = st.columns(2)

with insights_col1:
    st.markdown("#### 🎓 What the AI Learned")
    for domain, prog in progress.items():
        if prog["total_attempts"] > 0:
            optimal_strat = DOMAIN_TRUTH[domain]
            rate = prog["optimal_selection_rate"]
            
            if rate > 70:
                emoji = "✅"
                status = "LEARNED"
            elif rate > 40:
                emoji = "🔄"
                status = "LEARNING"
            else:
                emoji = "🔍"
                status = "EXPLORING"
            
            st.markdown(f"{emoji} **{domain}**: {status} ({rate:.1f}% optimal) - Best: `{optimal_strat}`")

with insights_col2:
    st.markdown("#### Next Steps")
    for domain, prog in progress.items():
        if prog["total_attempts"] < 10:
            st.markdown(f" **{domain}**: Need more data ({prog['total_attempts']} attempts)")
        elif prog["optimal_selection_rate"] < 50:
            st.markdown(f" **{domain}**: Still exploring alternatives")
        else:
            st.markdown(f" **{domain}**: Converged on optimal strategy")

# Auto-refresh
if auto_refresh:
    time.sleep(2)
    st.rerun()

# Footer
st.markdown("---")
st.markdown("**Live Dashboard** - Auto-refreshing every 2 seconds | Backend: http://localhost:8000 | Dashboard API: http://localhost:8001")
