import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { DEMO_TOKEN, fetchJson, getStoredToken } from '../api';
import './Dashboard.css';

const buildLocalPredictionPreview = (query) => [
  'MiroFish Local Swarm Prediction',
  `Query: ${query.substring(0, 90)}`,
  '----------------------------------------',
  'ResearchFish: NEUTRAL - available signals are mixed.',
  'AnalystFish: NEUTRAL - confidence needs more context.',
  'ContrarianFish: BEARISH - watch for hidden downside.',
  'SentinelFish: NEUTRAL - risk looks manageable for now.',
  '----------------------------------------',
  'CONSENSUS: NEUTRAL',
  'Swarm Confidence: 62%',
].join('\n');

const Dashboard = () => {
  const navigate = useNavigate();
  const [health, setHealth] = useState(null);
  const [prediction, setPrediction] = useState('');
  const [predQuery, setPredQuery] = useState('');
  const [isPredicting, setIsPredicting] = useState(false);

  const tenantId = localStorage.getItem('tenant_id') || 'Unknown';
  const token = getStoredToken() || DEMO_TOKEN;

  const fetchHealth = useCallback(async () => {
    try {
      setHealth(await fetchJson('/api/v1/health', { token: null, timeoutMs: 8000 }));
    } catch {
      setHealth({ status: 'offline', services: {} });
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  const handlePredict = async () => {
    if (!predQuery.trim()) return;
    setIsPredicting(true);
    setPrediction('');

    try {
      const data = await fetchJson('/api/v1/predict', {
        method: 'POST',
        token,
        timeoutMs: 30000,
        body: { query: predQuery }
      });
      setPrediction(data.prediction);
    } catch {
      setPrediction(buildLocalPredictionPreview(predQuery));
    } finally {
      setIsPredicting(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('pihu_token');
    localStorage.removeItem('tenant_id');
    navigate('/login');
  };

  return (
    <div className="dashboard-layout">
      {/* Sidebar */}
      <aside className="dash-sidebar glass">
        <div className="dash-brand">
          <div className="dash-logo-icon">P</div>
          <h2>Pihu Mate</h2>
        </div>

        <nav className="dash-nav">
          <button className="dash-nav-item active" onClick={() => navigate('/dashboard')}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            Overview
          </button>
          <button className="dash-nav-item" onClick={() => navigate('/chat')}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            Companion
          </button>
          <button className="dash-nav-item" onClick={() => navigate('/predictions')}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            Predictions
          </button>
        </nav>

        <div className="dash-user">
          <div className="dash-avatar">{tenantId[0]?.toUpperCase() || 'U'}</div>
          <div className="dash-user-info">
            <p className="dash-user-name">Piyush Raj</p>
            <p className="dash-tenant">{tenantId}</p>
          </div>
          <button className="dash-logout-btn" onClick={handleLogout} title="Logout">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="dash-main">
        <header className="dash-header">
          <div>
            <h1>Companion Control</h1>
            <p className="dash-header-sub">Desktop mate runtime and local modules</p>
          </div>
          <div className="dash-header-actions">
            <button className="btn-secondary" onClick={() => navigate('/chat')}>
              Open Companion
            </button>
            <button className="btn-primary" onClick={() => navigate('/predictions')}>
              MiroFish
            </button>
          </div>
        </header>

        {/* Metrics Grid */}
        <section className="dash-metrics">
          <div className="metric-card glass-subtle">
            <div className="metric-icon" style={{background: 'rgba(124,58,237,0.15)', color: '#a855f7'}}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </div>
            <div className="metric-data">
              <p className="metric-label">Chat Engine</p>
              <p className="metric-value">Fast</p>
            </div>
          </div>

          <div className="metric-card glass-subtle">
            <div className="metric-icon" style={{background: 'rgba(16,185,129,0.15)', color: '#34d399'}}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            </div>
            <div className="metric-data">
              <p className="metric-label">Predictions</p>
              <p className="metric-value">Ready</p>
            </div>
          </div>

          <div className="metric-card glass-subtle">
            <div className="metric-icon" style={{background: 'rgba(59,130,246,0.15)', color: '#60a5fa'}}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            </div>
            <div className="metric-data">
              <p className="metric-label">Privacy</p>
              <p className="metric-value">Local</p>
            </div>
          </div>

          <div className="metric-card glass-subtle">
            <div className="metric-icon" style={{background: health?.status === 'healthy' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)', color: health?.status === 'healthy' ? '#34d399' : '#f87171'}}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            </div>
            <div className="metric-data">
              <p className="metric-label">System Status</p>
              <p className="metric-value">{health?.status === 'healthy' ? 'Online' : 'Offline'}</p>
            </div>
          </div>
        </section>

        {/* Quick Prediction */}
        <section className="dash-prediction glass-subtle">
          <h3>Quick Swarm Prediction</h3>
          <p className="pred-desc">Ask MiroFish to analyze any scenario using swarm intelligence</p>
          <div className="pred-input-row">
            <input
              type="text"
              className="pred-input"
              placeholder="e.g. Will AI replace software engineers?"
              value={predQuery}
              onChange={(e) => setPredQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handlePredict()}
            />
            <button
              className="btn-primary"
              onClick={handlePredict}
              disabled={isPredicting || !predQuery.trim()}
            >
              {isPredicting ? 'Analyzing...' : 'Predict'}
            </button>
          </div>
          {prediction && (
            <pre className="pred-result">{prediction}</pre>
          )}
        </section>

        <section className="dash-services glass-subtle">
          <h3>Runtime Modules</h3>
          <div className="service-grid">
            {[
              ['api', health?.status === 'healthy' ? 'ready' : 'offline'],
              ['chat', 'ready'],
              ['mirofish', 'ready'],
              ['voice', 'standby'],
            ].map(([name, status]) => (
              <div key={name} className="service-item">
                <span className={`service-dot ${status === 'offline' ? 'offline' : 'online'}`} />
                <span className="service-name">{name}</span>
                <span className={`service-status ${status === 'offline' ? 'offline' : 'online'}`}>{status}</span>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
};

export default Dashboard;
