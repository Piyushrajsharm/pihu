import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import Predictions from './pages/Predictions';
import { decodeJwtPayload, DEMO_TOKEN, getStoredToken } from './api';
import './index.css';

// Protected Route Wrapper
const isTokenPresentAndFresh = () => {
  const token = getStoredToken();
  if (!token) return false;
  if (token === DEMO_TOKEN) return import.meta.env.VITE_ENABLE_DEMO_MODE === '1';

  const payload = decodeJwtPayload(token);
  return Boolean(payload && (!payload.exp || payload.exp * 1000 > Date.now()));
};

const ProtectedRoute = ({ children }) => {
  const isAuthenticated = isTokenPresentAndFresh();
  return isAuthenticated ? children : <Navigate to="/login" />;
};

function App() {
  return (
    <Router>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={<Login />} />

        {/* Protected Enterprise Routes */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <Chat />
            </ProtectedRoute>
          }
        />
        <Route
          path="/predictions"
          element={
            <ProtectedRoute>
              <Predictions />
            </ProtectedRoute>
          }
        />

        {/* Root Redirect */}
        <Route path="/" element={<Navigate to="/chat" />} />
      </Routes>
    </Router>
  );
}

export default App;
