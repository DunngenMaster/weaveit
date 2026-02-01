/**
 * WeavelT Live Dashboard - Real-time WebSocket Client
 * 
 * Connects to WebSocket and updates UI with live system events.
 * NO FALLBACKS - Pure real-time streaming.
 */

let ws = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 999999; // Effectively infinite

// Stats counters
let stats = {
    totalEvents: 0,
    banditCount: 0,
    judgeCount: 0,
    rewardCount: 0,
    csaCount: 0,
    memoryCount: 0
};

// Strategy performance tracking for chart
let strategyData = {
    labels: [],
    datasets: [
        {
            label: 'S1_CLARIFY_FIRST',
            data: [],
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            tension: 0.4
        },
        {
            label: 'S2_THREE_VARIANTS',
            data: [],
            borderColor: '#f59e0b',
            backgroundColor: 'rgba(245, 158, 11, 0.1)',
            tension: 0.4
        },
        {
            label: 'S3_TEMPLATE_FIRST',
            data: [],
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            tension: 0.4
        },
        {
            label: 'S4_STEPWISE',
            data: [],
            borderColor: '#8b5cf6',
            backgroundColor: 'rgba(139, 92, 246, 0.1)',
            tension: 0.4
        }
    ]
};

let strategyChart = null;

// Initialize Chart.js
function initChart() {
    const ctx = document.getElementById('strategyChart').getContext('2d');
    strategyChart = new Chart(ctx, {
        type: 'line',
        data: strategyData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: '#e0e0e0'
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#9ca3af' },
                    grid: { color: '#2d3561' }
                },
                y: {
                    ticks: { color: '#9ca3af' },
                    grid: { color: '#2d3561' },
                    beginAtZero: true
                }
            },
            animation: {
                duration: 500
            }
        }
    });
}

// Connect to WebSocket
function connect() {
    const wsUrl = 'ws://localhost:8001/ws/events';
    console.log('Connecting to', wsUrl);
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('✅ WebSocket connected');
        reconnectAttempts = 0;
        updateStatus(true, 'Connected - Streaming Live');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleEvent(data);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateStatus(false, 'Connection Error');
    };
    
    ws.onclose = () => {
        console.log('❌ WebSocket disconnected');
        updateStatus(false, 'Disconnected - Reconnecting...');
        
        // Auto-reconnect
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            setTimeout(() => {
                console.log(`Reconnect attempt ${reconnectAttempts}...`);
                connect();
            }, 2000);
        }
    };
}

// Update connection status
function updateStatus(connected, text) {
    const dot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    
    if (connected) {
        dot.classList.remove('disconnected');
        statusText.textContent = text;
    } else {
        dot.classList.add('disconnected');
        statusText.textContent = text;
    }
}

// Handle incoming events
function handleEvent(event) {
    // Skip heartbeats for display
    if (event.event_type === 'heartbeat') {
        return;
    }
    
    // Update stats
    stats.totalEvents++;
    
    if (event.event_type === 'bandit_selection') {
        stats.banditCount++;
        handleBanditSelection(event);
    } else if (event.event_type === 'judge_evaluation') {
        stats.judgeCount++;
        handleJudgeEvaluation(event);
    } else if (event.event_type === 'reward_update') {
        stats.rewardCount++;
        handleRewardUpdate(event);
    } else if (event.event_type === 'csa_created') {
        stats.csaCount++;
    } else if (event.event_type === 'memory_write') {
        stats.memoryCount++;
    }
    
    // Update stats display
    updateStatsDisplay();
    
    // Add to event feed
    addEventToFeed(event);
}

// Handle bandit selection events
function handleBanditSelection(event) {
    const { strategy, domain, ucb_scores } = event;
    
    // Update UCB score bars
    if (ucb_scores) {
        const maxScore = Math.max(...Object.values(ucb_scores));
        
        Object.entries(ucb_scores).forEach(([strat, score]) => {
            const shortStrat = strat.replace('S1_CLARIFY_FIRST', 'S1')
                                    .replace('S2_THREE_VARIANTS', 'S2')
                                    .replace('S3_TEMPLATE_FIRST', 'S3')
                                    .replace('S4_STEPWISE', 'S4');
            
            const fill = document.getElementById(`ucb-${shortStrat}`);
            if (fill) {
                const percentage = maxScore > 0 ? (score / maxScore) * 100 : 0;
                fill.style.width = `${percentage}%`;
                fill.textContent = score.toFixed(2);
            }
        });
    }
    
    // Update chart
    updateStrategyChart(strategy);
}

// Handle judge evaluation events
function handleJudgeEvaluation(event) {
    const { score } = event;
    // Could add a separate judge scores chart here
}

// Handle reward update events
function handleRewardUpdate(event) {
    const { strategy, reward } = event;
    // Track cumulative rewards per strategy
}

// Update strategy performance chart
function updateStrategyChart(selectedStrategy) {
    const now = new Date().toLocaleTimeString();
    
    // Add timestamp
    strategyData.labels.push(now);
    
    // Keep only last 20 data points
    if (strategyData.labels.length > 20) {
        strategyData.labels.shift();
    }
    
    // Update each strategy's data
    strategyData.datasets.forEach((dataset) => {
        if (dataset.label === selectedStrategy) {
            dataset.data.push((dataset.data[dataset.data.length - 1] || 0) + 1);
        } else {
            dataset.data.push(dataset.data[dataset.data.length - 1] || 0);
        }
        
        // Keep only last 20 data points
        if (dataset.data.length > 20) {
            dataset.data.shift();
        }
    });
    
    // Update chart
    if (strategyChart) {
        strategyChart.update('none'); // 'none' = no animation for smoother real-time updates
    }
}

// Update stats display
function updateStatsDisplay() {
    document.getElementById('totalEvents').textContent = stats.totalEvents;
    document.getElementById('banditCount').textContent = stats.banditCount;
    document.getElementById('judgeCount').textContent = stats.judgeCount;
    document.getElementById('rewardCount').textContent = stats.rewardCount;
    document.getElementById('csaCount').textContent = stats.csaCount;
}

// Add event to feed
function addEventToFeed(event) {
    const feed = document.getElementById('eventFeed');
    
    // Create event item
    const item = document.createElement('div');
    item.className = `event-item ${event.event_type}`;
    
    const eventType = document.createElement('div');
    eventType.className = 'event-type';
    eventType.textContent = event.event_type.replace('_', ' ');
    
    const eventData = document.createElement('div');
    eventData.className = 'event-data';
    eventData.textContent = formatEventData(event);
    
    const eventTime = document.createElement('div');
    eventTime.className = 'event-time';
    eventTime.textContent = new Date(event.timestamp).toLocaleTimeString();
    
    item.appendChild(eventType);
    item.appendChild(eventData);
    item.appendChild(eventTime);
    
    // Insert at top
    feed.insertBefore(item, feed.firstChild);
    
    // Keep only last 50 events
    while (feed.children.length > 50) {
        feed.removeChild(feed.lastChild);
    }
}

// Format event data for display
function formatEventData(event) {
    switch (event.event_type) {
        case 'bandit_selection':
            return `Selected: ${event.strategy} for domain: ${event.domain} | UCB: ${JSON.stringify(event.ucb_scores || {})}`;
        
        case 'judge_evaluation':
            return `Run: ${event.run_id} | Score: ${event.score} | Criteria: ${event.criteria}`;
        
        case 'reward_update':
            return `Run: ${event.run_id} | Reward: ${event.reward > 0 ? '+' : ''}${event.reward} | Total: ${event.total_rewards}`;
        
        case 'strategy_change':
            return `Changed: ${event.old} → ${event.new} | Reason: ${event.reason}`;
        
        case 'memory_write':
            return `Kind: ${event.kind} | Key: ${event.key} | Confidence: ${event.confidence}`;
        
        case 'csa_created':
            return `CSA: ${event.csa_id} | Title: ${event.title} | Trigger: ${event.trigger}`;
        
        case 'connection':
            return event.message;
        
        default:
            return JSON.stringify(event);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    connect();
});
