import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DEMO_TOKEN, fetchJson } from '../api';
import './Login.css';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const demoModeEnabled = import.meta.env.VITE_ENABLE_DEMO_MODE === '1';

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please fill in all fields');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const data = await fetchJson('/api/v1/auth/login', {
        method: 'POST',
        token: null,
        timeoutMs: 20000,
        body: { email, password },
      });

      localStorage.setItem('pihu_token', data.token);
      localStorage.setItem('tenant_id', data.tenant_id);
      navigate('/chat');
    } catch (err) {
      setError(err.message || 'Backend unavailable. Please start the API and try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDemoMode = () => {
    localStorage.setItem('pihu_token', DEMO_TOKEN);
    localStorage.setItem('tenant_id', 'tenant_demo');
    navigate('/chat');
  };

  return (
    <div className="login-page mate-login-page">
      <div className="login-desktop-preview" aria-hidden="true">
        <div className="login-preview-window">
          <span />
          <span />
          <span />
        </div>
        <img src="/pihu-avatar.webp" alt="" className="login-preview-avatar" />
        <div className="login-preview-ledge">Pihu is waiting</div>
      </div>

      <div className="login-card glass mate-login-card">
        <div className="login-logo">
          <div className="logo-orb">
            <span>P</span>
          </div>
          <h1>Pihu</h1>
          <p className="login-subtitle">Desktop companion session</p>
        </div>

        <form onSubmit={handleLogin} className="login-form">
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          {error && <p className="error-text">{error}</p>}

          <button type="submit" className="btn-login" disabled={isLoading}>
            {isLoading ? (
              <span className="spinner" />
            ) : (
              'Initialize Session'
            )}
          </button>
        </form>

        {demoModeEnabled && (
          <>
            <div className="login-divider">
              <span>or</span>
            </div>

            <button className="btn-demo" onClick={handleDemoMode}>
              Launch Demo Mode
            </button>
          </>
        )}

        <div className="login-footer">
            <span className="footer-text">Local-first companion workspace</span>
        </div>
      </div>
    </div>
  );
};

export default Login;
