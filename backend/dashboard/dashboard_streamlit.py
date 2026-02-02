"""
🚀 WeaveIt Real-Time Self-Learning Dashboard

Shows:
- Active agent runs in real-time
- Learning progression (policies evolving)
- Redis data flow (what's stored, how it changes)
- Weaviate knowledge growth  
- Feedback → Learning → Improvement cycle

Run: streamlit run backend/dashboard/dashboard_streamlit.py
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
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "WeaveIt Self-Learning AI Agent Dashboard"
    }
)

# ============= LIGHT THEME CSS =============
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    * {
        font-family: 'Inter', sans-serif;
    }
    
    /* Force light theme */
    .stApp {
        background: linear-gradient(135deg, #f0f4f8 0%, #d9e2ec 100%);
    }
    
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e2e8f0;
    }
    
    /* Metric cards */
    [data-testid="stMetricValue"] {
        font-size: 32px !important;
        font-weight: 700 !important;
        color: #1e293b !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #64748b !important;
        font-weight: 500 !important;
    }
    
    div[data-testid="metric-container"] {
        background: white !important;
        padding: 24px !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
        border: 1px solid #e2e8f0 !important;
    }
    
    /* Headers */
    h1, h2, h3, h4 {
        color: #1e293b !important;
        font-weight: 700 !important;
    }
    
    /* All text elements */
    p, span, div, label, li {
        color: #334155 !important;
    }
    
    /* Markdown text */
    .element-container p, .element-container span, .element-container div {
        color: #334155 !important;
    }
    
    /* Strong/bold text */
    strong, b {
        color: #1e293b !important;
    }
    
    /* Code blocks */
    code {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
        padding: 2px 6px;
        border-radius: 4px;
    }
    
    /* Custom status cards */
    .status-card {
        background: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.08);
        margin-bottom: 16px;
        border-left: 4px solid;
        color: #334155 !important;
        font-size: 14px;
        line-height: 1.6;
    }
    
    .status-card strong {
        color: #1e293b !important;
    }
    
    .status-card li {
        color: #475569 !important;
    }
    
    .running { border-left-color: #10b981; }
    .completed { border-left-color: #3b82f6; }
    .learning { border-left-color: #f59e0b; }
    .error { border-left-color: #ef4444; }
    
    /* Info boxes */
    .stAlert {
        background-color: #f0f9ff !important;
        border-left: 4px solid #3b82f6 !important;
        color: #1e40af !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background-color: white;
        border-radius: 8px;
        padding: 4px;
    }
    
    .stTabs [data-baseweb="tab"] {
        color: #64748b !important;
        font-weight: 500;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #3b82f6 !important;
        color: white !important;
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ============= HELPER FUNCTIONS =============

def get_redis_stats():
    """Get Redis memory usage and key counts"""
    try:
        client = redis_client.get_client()
        info = client.info('memory')
        
        # Count keys by pattern
        run_keys = len(list(client.scan_iter('run:*', count=1000)))
        tab_keys = len(list(client.scan_iter('tab:*', count=1000)))
        
        return {
            'memory_used_mb': round(info.get('used_memory', 0) / 1024 / 1024, 2),
            'total_keys': client.dbsize(),
            'run_keys': run_keys,
            'tab_keys': tab_keys,
            'connected': True
        }
    except Exception as e:
        return {'connected': False, 'error': str(e)}


def get_weaviate_stats():
    """Get Weaviate collection stats"""
    try:
        client = weaviate_client.client
        if not client.is_ready():
            return {'connected': False}
        
        stats = {}
        collections = ['RunMemory', 'RunTrace', 'RunFeedback', 'SkillMemory', 'ArtifactSummary']
        
        for collection_name in collections:
            if client.collections.exists(collection_name):
                collection = client.collections.get(collection_name)
                # Get aggregate count
                result = collection.aggregate.over_all(total_count=True)
                stats[collection_name] = result.total_count if result else 0
            else:
                stats[collection_name] = 0
        
        return {'connected': True, 'collections': stats}
    except Exception as e:
        return {'connected': False, 'error': str(e)}


def get_active_runs():
    """Get all active and recent runs from Redis"""
    try:
        client = redis_client.get_client()
        runs = []
        
        # Scan for all run keys
        for key in client.scan_iter('run:*', count=100):
            if ':' in key and not any(x in key for x in ['events', 'policy', 'feedback', 'patch']):
                # This is a main run key
                data = client.hgetall(key)
                if data:
                    run_id = key.replace('run:', '')
                    runs.append({
                        'run_id': run_id,
                        'status': data.get('status', 'unknown'),
                        'goal': data.get('goal', ''),
                        'query': data.get('query', ''),
                        'started_at': int(data.get('started_at', 0)),
                        'completed_at': int(data.get('completed_at', 0)) if data.get('completed_at') else None,
                        'tab_id': data.get('tab_id', ''),
                        'policy_json': data.get('policy_json', '{}'),
                        'summary': data.get('summary', '{}')
                    })
        
        # Sort by started_at descending
        runs.sort(key=lambda x: x['started_at'], reverse=True)
        return runs[:20]  # Return last 20 runs
    except Exception as e:
        st.error(f"Error fetching runs: {e}")
        return []


def get_learning_patches():
    """Get all tab patches (learning deltas)"""
    try:
        client = redis_client.get_client()
        patches = []
        
        for key in client.scan_iter('tab:*:patch', count=100):
            data = client.hgetall(key)
            if data and data.get('patch'):
                tab_id = key.split(':')[1]
                patch_data = json.loads(data.get('patch', '{}'))
                patches.append({
                    'tab_id': tab_id,
                    'policy_delta': patch_data.get('policy_delta', {}),
                    'prompt_delta': patch_data.get('prompt_delta', {}),
                    'rationale': patch_data.get('rationale', ''),
                    'timestamp': int(data.get('ts', 0))
                })
        
        patches.sort(key=lambda x: x['timestamp'], reverse=True)
        return patches
    except Exception as e:
        return []


def get_tab_preferences():
    """Get all tab preferences"""
    try:
        client = redis_client.get_client()
        prefs = []
        
        for key in client.scan_iter('tab:*:preferences', count=100):
            data = client.hgetall(key)
            if data:
                tab_id = key.split(':')[1]
                prefs.append({
                    'tab_id': tab_id,
                    'last_goal': data.get('last_goal', ''),
                    'last_query': data.get('last_query', ''),
                    'last_status': data.get('last_status', ''),
                    'policy_max_tabs': data.get('policy_max_tabs', ''),
                    'policy_min_score': data.get('policy_min_score', ''),
                })
        
        return prefs
    except Exception as e:
        return []


def get_weaviate_recent_memories(limit=10):
    """Get recent RunMemory entries"""
    try:
        client = weaviate_client.client
        if not client.is_ready() or not client.collections.exists('RunMemory'):
            return []
        
        collection = client.collections.get('RunMemory')
        results = collection.query.fetch_objects(limit=limit)
        
        memories = []
        for obj in results.objects:
            props = obj.properties
            memories.append({
                'run_id': props.get('run_id', ''),
                'goal': props.get('goal', ''),
                'query': props.get('query', ''),
                'summary_text': props.get('summary_text', ''),
                'policy_json': props.get('policy_json', '{}'),
                'created_at': props.get('created_at', '')
            })
        
        return memories
    except Exception as e:
        return []


# ============= HEADER =============
st.title("WeaveIt Self-Learning Dashboard")
st.markdown("Real-time AI agent learning visualization")

# ============= SIDEBAR =============
st.sidebar.title("Dashboard Controls")
auto_refresh = st.sidebar.checkbox("Auto-refresh (2s)", value=True)
show_redis_keys = st.sidebar.checkbox("Show Redis keys", value=False)
show_raw_data = st.sidebar.checkbox("Show raw JSON", value=False)

st.sidebar.markdown("---")
st.sidebar.markdown("### System Status")

# Redis status
redis_stats = get_redis_stats()
if redis_stats.get('connected'):
    st.sidebar.success("Redis Connected")
    st.sidebar.metric("Memory", f"{redis_stats['memory_used_mb']} MB")
    st.sidebar.metric("Keys", redis_stats['total_keys'])
else:
    st.sidebar.error("Redis Disconnected")

# Weaviate status
weaviate_stats = get_weaviate_stats()
if weaviate_stats.get('connected'):
    st.sidebar.success("Weaviate Connected")
    total_objects = sum(weaviate_stats['collections'].values())
    st.sidebar.metric("Objects", total_objects)
else:
    st.sidebar.error("Weaviate Disconnected")

st.sidebar.markdown("---")
refresh_btn = st.sidebar.button("Manual Refresh")

# ============= MAIN METRICS =============
st.markdown("### System Overview")

col1, col2, col3, col4, col5 = st.columns(5)

active_runs = get_active_runs()
running_count = len([r for r in active_runs if r['status'] == 'running'])
completed_count = len([r for r in active_runs if r['status'] == 'completed'])
patches = get_learning_patches()

with col1:
    st.metric("Active Runs", running_count)

with col2:
    st.metric("Completed", completed_count)

with col3:
    st.metric("Total Runs", len(active_runs))

with col4:
    st.metric("Learning Patches", len(patches))

with col5:
    if weaviate_stats.get('connected'):
        total_weaviate = sum(weaviate_stats['collections'].values())
        st.metric("Weaviate Objects", total_weaviate)
    else:
        st.metric("Weaviate Objects", "N/A")

# Data flow visualization
st.markdown("---")
st.markdown("### Data Architecture")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div class="status-card running">
        <h4 style="margin:0 0 12px 0; color:#10b981;">REDIS - Hot Memory</h4>
        <strong>Stores:</strong>
        <ul style="margin:8px 0; padding-left:20px;">
            <li>Run status & results</li>
            <li>Active policies</li>
            <li>Event streams</li>
            <li>Learning patches</li>
        </ul>
        <strong>Retention:</strong> 24 hours<br/>
        <strong>Keys:</strong> {run_keys} runs, {tab_keys} tabs
    </div>
    """.format(
        run_keys=redis_stats.get('run_keys', 0) if redis_stats.get('connected') else 0,
        tab_keys=redis_stats.get('tab_keys', 0) if redis_stats.get('connected') else 0
    ), unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="status-card completed">
        <h4 style="margin:0 0 12px 0; color:#3b82f6;">WEAVIATE - Long-term Memory</h4>
        <strong>Stores:</strong>
        <ul style="margin:8px 0; padding-left:20px;">
            <li>Learned policies</li>
            <li>Execution traces</li>
            <li>User feedback</li>
            <li>Transferable skills</li>
        </ul>
        <strong>Retention:</strong> Permanent<br/>
        <strong>Search:</strong> BM25 semantic
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="status-card learning">
        <h4 style="margin:0 0 12px 0; color:#f59e0b;">GEMINI - AI Processing</h4>
        <strong>Per Run:</strong>
        <ul style="margin:8px 0; padding-left:20px;">
            <li>Plan: 1 call</li>
            <li>Score: 1 call</li>
            <li>Extract: 3-11 calls</li>
            <li>Summarize: 1 call</li>
            <li>Learn: 1 call (on feedback)</li>
        </ul>
        <strong>Model:</strong> gemini-2.5-flash<br/>
        <strong>Total:</strong> 7-15 calls/run
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ============= ACTIVE RUNS =============
st.markdown("### Active Runs")

if not active_runs:
    st.info("No runs yet. Start a run from the Electron app.")
else:
    # Create tabs for different views
    tab1, tab2 = st.tabs(["List View", "Timeline"])
    
    with tab1:
        for run in active_runs[:10]:
            status_icon = {
                'running': '●',
                'completed': '●',
                'error': '●',
                'paused': '●'
            }.get(run['status'], '○')
            
            # Calculate duration
            started = run['started_at']
            completed = run['completed_at']
            if completed:
                duration = (completed - started) / 1000
                duration_str = f"{duration:.1f}s"
            else:
                duration_str = "Running"
            
            # Parse policy
            try:
                policy = json.loads(run['policy_json'])
                policy_str = f"tabs:{policy.get('max_tabs', 'N/A')}, score:{policy.get('min_score', 'N/A')}"
            except:
                policy_str = "Default"
            
            st.markdown(f"""
            <div class="status-card {run['status']}">
                <strong>{status_icon} {run['status'].upper()}</strong> | 
                ID: <code>{run['run_id'][:8]}</code> | 
                Tab: <code>{run['tab_id'][:8] if run['tab_id'] else 'N/A'}</code>
                <br/>
                <strong>Goal:</strong> {run['goal'][:60]}<br/>
                <strong>Query:</strong> {run['query'][:60]}<br/>
                <strong>Policy:</strong> {policy_str} | <strong>Duration:</strong> {duration_str}
            </div>
            """, unsafe_allow_html=True)
    
    with tab2:
        # Timeline visualization
        if active_runs:
            df_timeline = pd.DataFrame([{
                'Run': r['run_id'][:8],
                'Goal': r['goal'][:30],
                'Start': datetime.fromtimestamp(r['started_at'] / 1000),
                'End': datetime.fromtimestamp(r['completed_at'] / 1000) if r['completed_at'] else datetime.now(),
                'Status': r['status']
            } for r in active_runs[:15]])
            
            fig = px.timeline(
                df_timeline,
                x_start='Start',
                x_end='End',
                y='Goal',
                color='Status',
                hover_data=['Run'],
                color_discrete_map={
                    'running': '#10b981',
                    'completed': '#3b82f6',
                    'error': '#ef4444',
                    'paused': '#f59e0b'
                }
            )
            fig.update_layout(
                height=400,
                xaxis_title="Time",
                yaxis_title="Run",
                showlegend=True,
                paper_bgcolor='white',
                plot_bgcolor='#f9fafb',
                font=dict(color='#1e293b', size=12),
                title_font=dict(color='#1e293b'),
                xaxis=dict(
                    title=dict(font=dict(color='#1e293b')),
                    tickfont=dict(color='#1e293b')
                ),
                yaxis=dict(
                    title=dict(font=dict(color='#1e293b')),
                    tickfont=dict(color='#1e293b')
                )
            )
            st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ============= LEARNING SECTION =============
st.markdown("### Learning Progress")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Learning Patches")
    if patches:
        for patch in patches[:5]:
            patch_time = datetime.fromtimestamp(patch['timestamp'] / 1000).strftime('%H:%M:%S')
            st.markdown(f"""
            <div class="status-card learning">
                <strong>Tab:</strong> <code>{patch['tab_id'][:12]}</code> | <strong>Time:</strong> {patch_time}
                <br/>
                <strong>Changes:</strong> {json.dumps(patch['policy_delta'])}
                <br/>
                <strong>Reason:</strong> {patch['rationale'][:80]}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No patches yet. Submit feedback to teach the agent.")

with col2:
    st.markdown("#### Tab Preferences")
    prefs = get_tab_preferences()
    if prefs:
        for pref in prefs[:5]:
            st.markdown(f"""
            <div class="status-card completed">
                <strong>Tab:</strong> <code>{pref['tab_id'][:12]}</code>
                <br/>
                <strong>Goal:</strong> {pref['last_goal'][:40]}
                <br/>
                <strong>Policy:</strong> tabs={pref['policy_max_tabs']}, score={pref['policy_min_score']}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No preferences saved yet.")

st.markdown("---")

# ============= POLICY EVOLUTION =============
st.markdown("### Policy Evolution")

# Analyze how policies have changed over time
policy_history = []
for run in active_runs:
    try:
        policy = json.loads(run['policy_json'])
        policy_history.append({
            'timestamp': run['started_at'],
            'max_tabs': int(policy.get('max_tabs', 11)),
            'min_score': float(policy.get('min_score', 0.55)),
            'goal': run['goal'][:20]
        })
    except:
        pass

if policy_history:
    df_policy = pd.DataFrame(policy_history)
    df_policy['time'] = pd.to_datetime(df_policy['timestamp'], unit='ms')
    df_policy = df_policy.sort_values('time')
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.line(
            df_policy,
            x='time',
            y='max_tabs',
            title='Max Tabs Over Time',
            markers=True
        )
        fig.update_layout(
            height=300,
            paper_bgcolor='white',
            plot_bgcolor='#f9fafb',
            font=dict(color='#1e293b'),
            title_font=dict(color='#1e293b'),
            xaxis=dict(color='#1e293b'),
            yaxis=dict(color='#1e293b')
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.line(
            df_policy,
            x='time',
            y='min_score',
            title='Min Score Over Time',
            markers=True
        )
        fig.update_layout(
            height=300,
            paper_bgcolor='white',
            plot_bgcolor='#f9fafb',
            font=dict(color='#1e293b'),
            title_font=dict(color='#1e293b'),
            xaxis=dict(color='#1e293b'),
            yaxis=dict(color='#1e293b')
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No policy data yet. Run agents to see evolution.")

# ============= WEAVIATE COLLECTIONS =============
if weaviate_stats.get('connected'):
    st.markdown("---")
    st.markdown("### Weaviate Collections")
    
    collections_data = weaviate_stats['collections']
    df_collections = pd.DataFrame([
        {'Collection': k, 'Objects': v}
        for k, v in collections_data.items()
    ])
    
    fig = px.bar(
        df_collections,
        x='Collection',
        y='Objects',
        text='Objects',
        color='Objects',
        color_continuous_scale='Blues'
    )
    fig.update_layout(
        height=300,
        showlegend=False,
        paper_bgcolor='white',
        plot_bgcolor='#f9fafb',
        font=dict(color='#1e293b'),
        xaxis=dict(color='#1e293b'),
        yaxis=dict(color='#1e293b')
    )
    st.plotly_chart(fig, use_container_width=True)

# ============= REDIS KEYS DEBUG =============
if show_redis_keys:
    st.markdown("---")
    st.markdown("### Redis Keys")
    
    try:
        client = redis_client.get_client()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Run Keys**")
            run_keys = list(client.scan_iter('run:*', count=20))
            for key in run_keys[:10]:
                st.code(key, language='text')
        
        with col2:
            st.markdown("**Tab Keys**")
            tab_keys = list(client.scan_iter('tab:*', count=20))
            for key in tab_keys[:10]:
                st.code(key, language='text')
    except Exception as e:
        st.error(f"Error: {e}")

# ============= FOOTER =============
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**Live Dashboard**")
with col2:
    st.markdown(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
with col3:
    st.markdown("Backend: http://localhost:8000")

# ============= AUTO REFRESH =============
if auto_refresh:
    time.sleep(2)
    st.rerun()