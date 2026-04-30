import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DEMO_TOKEN, fetchJson, getStoredToken } from '../api';
import './Predictions.css';

const SCENARIOS = [
  { id: 'neutral', label: 'Neutral', emoji: '⚖️', color: '#94a3b8' },
  { id: 'bullish', label: 'Bullish', emoji: '📈', color: '#34d399' },
  { id: 'bearish', label: 'Bearish', emoji: '📉', color: '#f87171' },
  { id: 'shock', label: 'Black Swan', emoji: '🦢', color: '#fbbf24' },
];

const FISH_AGENTS = [
  { name: 'ResearchFish', emoji: '🔬', role: 'Factual Analysis', color: '#60a5fa' },
  { name: 'AnalystFish', emoji: '📊', role: 'Pattern Recognition', color: '#a78bfa' },
  { name: 'ContrarianFish', emoji: '🔥', role: 'Devil\'s Advocate', color: '#fb923c' },
  { name: 'SentinelFish', emoji: '🛡️', role: 'Risk Assessment', color: '#34d399' },
];

const Predictions = () => {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [scenario, setScenario] = useState('neutral');
  const [result, setResult] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [activeAgents, setActiveAgents] = useState([]);
  const [history, setHistory] = useState([]);

  const token = getStoredToken() || DEMO_TOKEN;

  const runPrediction = async () => {
    if (!query.trim() || isRunning) return;

    setIsRunning(true);
    setResult(null);
    setActiveAgents([]);

    // Simulate agent activation animation
    for (let i = 0; i < FISH_AGENTS.length; i++) {
      await new Promise(r => setTimeout(r, 400));
      setActiveAgents(prev => [...prev, FISH_AGENTS[i].name]);
    }

    try {
      const data = await fetchJson('/api/v1/predict', {
        method: 'POST',
        token,
        timeoutMs: 30000,
        body: { query, scenario }
      });

      setResult({
        prediction: data.prediction,
        latency: data.latency_ms,
        agents: data.agents_used
      });
      setHistory(prev => [{
        query: query.substring(0, 60),
        scenario,
        timestamp: new Date().toLocaleTimeString(),
        ...data
      }, ...prev].slice(0, 10));
    } catch {
      // Offline fallback — simulate a local prediction
      const mockPrediction = generateMockPrediction(query, scenario);
      setResult(mockPrediction);
      setHistory(prev => [{
        query: query.substring(0, 60),
        scenario,
        timestamp: new Date().toLocaleTimeString(),
        ...mockPrediction
      }, ...prev].slice(0, 10));
    } finally {
      setIsRunning(false);
    }
  };

  const generateMockPrediction = (q, sc) => {
    const votes = { bullish: 0, bearish: 0, neutral: 0 };
    const agentResults = FISH_AGENTS.map(agent => {
      const vote = sc === 'bullish' ? 'bullish' : sc === 'bearish' ? 'bearish' : ['bullish', 'neutral', 'bearish'][Math.floor(Math.random() * 3)];
      votes[vote]++;
      return `${agent.emoji} ${agent.name}: ${vote.toUpperCase()} (${Math.floor(50 + Math.random() * 40)}%)`;
    });

    const consensus = Object.entries(votes).reduce((a, b) => a[1] > b[1] ? a : b)[0];

    return {
      prediction: [
        `🐟 MiroFish Swarm Prediction (Local Simulation)`,
        `📋 Query: ${q.substring(0, 60)}`,
        `🎯 Scenario: ${sc.toUpperCase()}`,
        '─'.repeat(40),
        ...agentResults,
        '─'.repeat(40),
        `🏆 CONSENSUS: ${consensus.toUpperCase()}`,
        `📊 Swarm Confidence: ${Math.floor(55 + Math.random() * 30)}%`,
        `⚡ Powered by MiroFish Swarm Intelligence`,
      ].join('\n'),
      latency: Math.floor(100 + Math.random() * 500),
      agents: 4
    };
  };

  return (
    <div className="pred-layout">
      {/* Sidebar */}
      <aside className="pred-sidebar glass">
        <div className="pred-brand">
          <div className="pred-logo">🐟</div>
          <h2>MiroFish</h2>
        </div>

        <nav className="pred-nav">
          <button className="dash-nav-item" onClick={() => navigate('/dashboard')}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            Dashboard
          </button>
          <button className="dash-nav-item" onClick={() => navigate('/chat')}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            Chat Agent
          </button>
          <button className="dash-nav-item active">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            Predictions
          </button>
        </nav>

        {/* Prediction History */}
        <div className="pred-history">
          <h4>History</h4>
          {history.length === 0 ? (
            <p className="pred-history-empty">No predictions yet</p>
          ) : (
            history.map((h, i) => (
              <div key={i} className="pred-history-item" onClick={() => { setQuery(h.query); }}>
                <span className="pred-history-query">{h.query}</span>
                <span className="pred-history-time">{h.timestamp}</span>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="pred-main">
        <header className="pred-header">
          <div>
            <h1>Swarm Intelligence</h1>
            <p className="pred-header-sub">Multi-agent consensus prediction engine</p>
          </div>
        </header>

        {/* Agent Cards */}
        <section className="agent-grid">
          {FISH_AGENTS.map((agent) => (
            <div
              key={agent.name}
              className={`agent-card glass-subtle ${activeAgents.includes(agent.name) ? 'active' : ''}`}
            >
              <div className="agent-emoji">{agent.emoji}</div>
              <div className="agent-info">
                <p className="agent-name">{agent.name}</p>
                <p className="agent-role">{agent.role}</p>
              </div>
              <div className="agent-status">
                {activeAgents.includes(agent.name) ? (
                  <span className="agent-active-dot" style={{ background: agent.color, boxShadow: `0 0 10px ${agent.color}` }} />
                ) : (
                  <span className="agent-idle-dot" />
                )}
              </div>
            </div>
          ))}
        </section>

        {/* Query Input */}
        <section className="pred-query-section glass-subtle">
          <h3>Prediction Query</h3>
          <input
            type="text"
            className="pred-query-input"
            placeholder="e.g. Will renewable energy stocks outperform tech in 2026?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runPrediction()}
            disabled={isRunning}
          />

          <div className="scenario-row">
            <span className="scenario-label">Scenario:</span>
            {SCENARIOS.map(s => (
              <button
                key={s.id}
                className={`scenario-btn ${scenario === s.id ? 'selected' : ''}`}
                onClick={() => setScenario(s.id)}
                style={{ '--sc-color': s.color }}
              >
                {s.emoji} {s.label}
              </button>
            ))}
          </div>

          <button
            className="btn-predict"
            onClick={runPrediction}
            disabled={isRunning || !query.trim()}
          >
            {isRunning ? (
              <>
                <span className="spinner" /> Swarm Analyzing...
              </>
            ) : (
              '🐟 Launch Swarm Prediction'
            )}
          </button>
        </section>

        {/* Result */}
        {result && (
          <section className="pred-result-section glass-subtle">
            <div className="pred-result-header">
              <h3>Swarm Consensus</h3>
              <div className="pred-result-meta">
                <span>{result.agents} agents</span>
                <span>•</span>
                <span>{result.latency}ms</span>
              </div>
            </div>
            <pre className="pred-result-output">{result.prediction}</pre>
          </section>
        )}
      </main>
    </div>
  );
};

export default Predictions;
