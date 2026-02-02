"""
WeaveIt Learning Metrics Dashboard 2.0

Focus: Show how the AI is actually improving through learning
- Score improvements over time
- Policy adjustments effectiveness  
- Feedback loop performance
- Before/After comparisons
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client

# ============= PAGE CONFIG =============
st.set_page_config(
    page_title="WeaveIt Learning Metrics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============= STYLES =============
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    * {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #e4e9f0 100%);
    }
    
    h1, h2, h3, h4 {
        color: #1e293b !important;
        font-weight: 700 !important;
    }
    
    p, span, div, label {
        color: #334155 !important;
    }
    
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 10px 0;
    }
    
    .improvement {
        color: #10b981 !important;
        font-weight: 600;
    }
    
    .decline {
        color: #ef4444 !important;
        font-weight: 600;
    }
    
    .neutral {
        color: #6b7280 !important;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 28px !important;
        font-weight: 700 !important;
        color: #1e293b !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-weight: 500 !important;
    }
</style>
""", unsafe_allow_html=True)

# ============= HELPER FUNCTIONS =============

def get_learning_metrics():
    """Get metrics showing learning effectiveness"""
    try:
        client = redis_client.get_client()
        
        # Get all runs
        run_keys = list(client.scan_iter('run:*', count=1000))
        run_keys = [k for k in run_keys if not k.endswith(b':patch') and not k.endswith(b':feedback') and not k.endswith(b':policy') and not k.endswith(b':events')]
        
        runs = []
        for key in run_keys:
            data = client.hgetall(key)
            if data and data.get('status'):
                runs.append({
                    'run_id': data.get('run_id', ''),
                    'tab_id': data.get('tab_id', ''),
                    'goal': data.get('goal', ''),
                    'started_at': int(data.get('started_at', 0)),
                    'policy_json': data.get('policy_json', '{}'),
                    'status': data.get('status', '')
                })
        
        # Get patches
        patch_keys = list(client.scan_iter('tab:*:patch', count=1000))
        patches = []
        for key in patch_keys:
            data = client.hgetall(key)
            if data and data.get('patch'):
                try:
                    patch = json.loads(data.get('patch', '{}'))
                    patches.append({
                        'tab_id': key.decode().split(':')[1],
                        'timestamp': int(data.get('ts', 0)),
                        'policy_delta': patch.get('policy_delta', {}),
                        'prompt_delta': patch.get('prompt_delta', {}),
                        'rationale': patch.get('rationale', '')
                    })
                except:
                    pass
        
        return {
            'runs': runs,
            'patches': patches,
            'total_runs': len(runs),
            'total_patches': len(patches)
        }
    except Exception as e:
        print(f"Error getting metrics: {e}")
        return {'runs': [], 'patches': [], 'total_runs': 0, 'total_patches': 0}


def analyze_policy_evolution(runs):
    """Analyze how policies have evolved over time"""
    if not runs:
        return None
    
    # Sort by timestamp
    sorted_runs = sorted(runs, key=lambda x: x['started_at'])
    
    evolution = []
    for run in sorted_runs:
        try:
            policy = json.loads(run['policy_json'])
            evolution.append({
                'timestamp': run['started_at'],
                'max_tabs': int(policy.get('max_tabs', 11)),
                'min_score': float(policy.get('min_score', 0.55)),
                'goal': run['goal'][:30]
            })
        except:
            pass
    
    return evolution


def calculate_learning_rate(patches):
    """Calculate how often the system is learning"""
    if not patches:
        return 0
    
    # Count patches in last 24 hours
    now = datetime.now().timestamp() * 1000
    day_ago = now - (24 * 60 * 60 * 1000)
    
    recent_patches = [p for p in patches if p['timestamp'] > day_ago]
    return len(recent_patches)


def get_tab_learning_history(tab_id):
    """Get learning history for a specific tab"""
    try:
        client = redis_client.get_client()
        
        # Get runs for this tab
        tab_runs_key = f"tab:{tab_id}:runs"
        run_ids = client.lrange(tab_runs_key, 0, -1)
        
        history = []
        for run_id in run_ids:
            if isinstance(run_id, bytes):
                run_id = run_id.decode()
            
            run_key = f"run:{run_id}"
            data = client.hgetall(run_key)
            
            if data:
                # Get patch if exists
                patch_key = f"run:{run_id}:patch"
                patch_data = client.hgetall(patch_key)
                patch = None
                if patch_data and patch_data.get('patch'):
                    try:
                        patch = json.loads(patch_data.get('patch', '{}'))
                    except:
                        pass
                
                history.append({
                    'run_id': run_id,
                    'timestamp': int(data.get('started_at', 0)),
                    'goal': data.get('goal', ''),
                    'policy': data.get('policy_json', '{}'),
                    'patch': patch,
                    'status': data.get('status', '')
                })
        
        return sorted(history, key=lambda x: x['timestamp'], reverse=True)
    except Exception as e:
        print(f"Error getting tab history: {e}")
        return []


# ============= HEADER =============
st.title("WeaveIt Learning Metrics Dashboard")
st.markdown("Tracking AI improvement through feedback loops")

# ============= SIDEBAR =============
st.sidebar.title("Controls")
auto_refresh = st.sidebar.checkbox("Auto-refresh (5s)", value=True)
show_raw = st.sidebar.checkbox("Show raw data", value=False)

st.sidebar.markdown("---")
st.sidebar.markdown("### Filter")
time_range = st.sidebar.selectbox("Time Range", ["Last Hour", "Last 24 Hours", "Last 7 Days", "All Time"])

# ============= MAIN METRICS =============
metrics_data = get_learning_metrics()

st.markdown("### Key Performance Indicators")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Runs", metrics_data['total_runs'])

with col2:
    st.metric("Learning Events", metrics_data['total_patches'])

with col3:
    learning_rate = calculate_learning_rate(metrics_data['patches'])
    st.metric("Patches (24h)", learning_rate)

with col4:
    if metrics_data['total_runs'] > 0:
        learn_ratio = (metrics_data['total_patches'] / metrics_data['total_runs']) * 100
        st.metric("Learning Rate", f"{learn_ratio:.1f}%")
    else:
        st.metric("Learning Rate", "0%")

# ============= POLICY EVOLUTION =============
st.markdown("---")
st.markdown("### Policy Evolution Over Time")

evolution = analyze_policy_evolution(metrics_data['runs'])

if evolution and len(evolution) > 1:
    df_evolution = pd.DataFrame(evolution)
    df_evolution['datetime'] = pd.to_datetime(df_evolution['timestamp'], unit='ms')
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Max Tabs Adjustment")
        fig = px.line(
            df_evolution,
            x='datetime',
            y='max_tabs',
            markers=True,
            hover_data=['goal']
        )
        fig.update_layout(
            height=300,
            showlegend=False,
            paper_bgcolor='white',
            plot_bgcolor='#f9fafb',
            xaxis_title="Time",
            yaxis_title="Max Tabs"
        )
        fig.add_hline(y=11, line_dash="dash", line_color="gray", annotation_text="Default (11)")
        st.plotly_chart(fig, use_container_width=True)
        
        # Show change
        initial = df_evolution.iloc[0]['max_tabs']
        current = df_evolution.iloc[-1]['max_tabs']
        change = current - initial
        if change > 0:
            st.markdown(f"<p class='improvement'>↑ Increased by {change} tabs</p>", unsafe_allow_html=True)
        elif change < 0:
            st.markdown(f"<p class='improvement'>↓ Decreased by {abs(change)} tabs (more focused)</p>", unsafe_allow_html=True)
        else:
            st.markdown(f"<p class='neutral'>No change</p>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("#### Min Score Threshold")
        fig = px.line(
            df_evolution,
            x='datetime',
            y='min_score',
            markers=True,
            hover_data=['goal']
        )
        fig.update_layout(
            height=300,
            showlegend=False,
            paper_bgcolor='white',
            plot_bgcolor='#f9fafb',
            xaxis_title="Time",
            yaxis_title="Min Score"
        )
        fig.add_hline(y=0.55, line_dash="dash", line_color="gray", annotation_text="Default (0.55)")
        st.plotly_chart(fig, use_container_width=True)
        
        # Show change
        initial = df_evolution.iloc[0]['min_score']
        current = df_evolution.iloc[-1]['min_score']
        change = current - initial
        if change > 0:
            st.markdown(f"<p class='improvement'>↑ Increased by {change:.2f} (higher quality)</p>", unsafe_allow_html=True)
        elif change < 0:
            st.markdown(f"<p class='decline'>↓ Decreased by {abs(change):.2f} (more permissive)</p>", unsafe_allow_html=True)
        else:
            st.markdown(f"<p class='neutral'>No change</p>", unsafe_allow_html=True)
else:
    st.info("Not enough data to show policy evolution. Run more searches and provide feedback.")

# ============= LEARNING PATCHES ANALYSIS =============
st.markdown("---")
st.markdown("### Learning Patches Applied")

if metrics_data['patches']:
    st.markdown(f"**{len(metrics_data['patches'])} patches generated from user feedback**")
    
    # Group by type of change
    policy_changes = defaultdict(int)
    prompt_changes = defaultdict(int)
    
    for patch in metrics_data['patches']:
        for key in patch['policy_delta'].keys():
            policy_changes[key] += 1
        for key in patch['prompt_delta'].keys():
            prompt_changes[key] += 1
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Policy Adjustments")
        if policy_changes:
            for param, count in policy_changes.items():
                st.markdown(f"- **{param}**: {count} adjustments")
        else:
            st.markdown("No policy adjustments yet")
    
    with col2:
        st.markdown("#### Prompt Modifications")
        if prompt_changes:
            for param, count in prompt_changes.items():
                st.markdown(f"- **{param}**: {count} modifications")
        else:
            st.markdown("No prompt modifications yet")
    
    # Recent patches
    st.markdown("#### Recent Learning Events")
    recent_patches = sorted(metrics_data['patches'], key=lambda x: x['timestamp'], reverse=True)[:5]
    
    for patch in recent_patches:
        timestamp = datetime.fromtimestamp(patch['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
        st.markdown(f"""
        <div class="metric-card">
            <strong>Tab:</strong> {patch['tab_id'][:12]} | <strong>Time:</strong> {timestamp}<br/>
            <strong>Policy:</strong> {json.dumps(patch['policy_delta'])}<br/>
            <strong>Prompt:</strong> {json.dumps(patch['prompt_delta'])}<br/>
            <strong>Reason:</strong> {patch['rationale']}
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No learning patches yet. Submit feedback to teach the system.")

# ============= TAB-SPECIFIC LEARNING =============
st.markdown("---")
st.markdown("### Tab-Specific Learning")

# Get unique tabs
tabs = set(run['tab_id'] for run in metrics_data['runs'] if run['tab_id'])

if tabs:
    selected_tab = st.selectbox("Select Tab", sorted(tabs))
    
    if selected_tab:
        history = get_tab_learning_history(selected_tab)
        
        if history:
            st.markdown(f"**{len(history)} runs in this tab**")
            
            # Show progression
            for i, item in enumerate(history[:10]):
                has_patch = item['patch'] is not None
                patch_indicator = "✓ Learned" if has_patch else "○ No feedback"
                
                timestamp = datetime.fromtimestamp(item['timestamp'] / 1000).strftime('%H:%M:%S')
                
                try:
                    policy = json.loads(item['policy'])
                    policy_str = f"tabs:{policy.get('max_tabs', 'N/A')}, score:{policy.get('min_score', 'N/A')}"
                except:
                    policy_str = "Default"
                
                st.markdown(f"""
                <div class="metric-card">
                    <strong>Run {len(history) - i}</strong> | {timestamp} | {patch_indicator}<br/>
                    <strong>Goal:</strong> {item['goal'][:60]}<br/>
                    <strong>Policy:</strong> {policy_str}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No history for this tab yet")
else:
    st.info("No tab data available")

# ============= WEAVIATE LONG-TERM MEMORY =============
st.markdown("---")
st.markdown("### Long-Term Memory (Weaviate)")

try:
    wclient = weaviate_client.client
    if wclient.is_ready():
        collections_data = {}
        for cname in ['RunMemory', 'RunTrace', 'RunFeedback']:
            if wclient.collections.exists(cname):
                collection = wclient.collections.get(cname)
                result = collection.aggregate.over_all(total_count=True)
                collections_data[cname] = result.total_count if result else 0
            else:
                collections_data[cname] = 0
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Learned Runs", collections_data.get('RunMemory', 0))
        
        with col2:
            st.metric("Execution Traces", collections_data.get('RunTrace', 0))
        
        with col3:
            st.metric("Feedback Entries", collections_data.get('RunFeedback', 0))
    else:
        st.warning("Weaviate not connected")
except Exception as e:
    st.error(f"Error accessing Weaviate: {e}")

# ============= RAW DATA =============
if show_raw:
    st.markdown("---")
    st.markdown("### Raw Data")
    
    with st.expander("Runs Data"):
        st.json(metrics_data['runs'][:5])
    
    with st.expander("Patches Data"):
        st.json(metrics_data['patches'][:5])

# ============= FOOTER =============
st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"**Last Updated:** {datetime.now().strftime('%H:%M:%S')}")
with col2:
    st.markdown("**Backend:** http://localhost:8000")

# ============= AUTO REFRESH =============
if auto_refresh:
    time.sleep(5)
    st.rerun()
