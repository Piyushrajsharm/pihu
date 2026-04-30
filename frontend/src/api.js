export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');
export const DEMO_TOKEN = 'dev-token';

export class ApiError extends Error {
  constructor(message, { status = 0, details = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

export const getStoredToken = () => localStorage.getItem('pihu_token');

export const createRequestId = () => {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
};

export const decodeJwtPayload = (token) => {
  const payload = token?.split('.')?.[1];
  if (!payload) return null;

  try {
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    return JSON.parse(window.atob(padded));
  } catch {
    return null;
  }
};

const buildUrl = (path) => {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
};

const readResponseBody = async (response) => {
  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
};

const getErrorMessage = (body, fallback) => {
  if (!body) return fallback;
  if (typeof body === 'string') return body;
  if (typeof body.detail === 'string') return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg || item.message || String(item)).join(', ');
  if (typeof body.message === 'string') return body.message;
  return fallback;
};

export const fetchJson = async (
  path,
  {
    method = 'GET',
    headers = {},
    body,
    token = getStoredToken(),
    timeoutMs = 30000,
    signal,
  } = {},
) => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  if (signal) {
    signal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  const requestHeaders = {
    ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...headers,
  };

  try {
    const response = await fetch(buildUrl(path), {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    const responseBody = await readResponseBody(response);
    if (!response.ok) {
      throw new ApiError(getErrorMessage(responseBody, `HTTP ${response.status}`), {
        status: response.status,
        details: responseBody,
      });
    }

    return responseBody;
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new ApiError('Request timed out. Backend ne response time pe nahi diya.', { status: 408 });
    }
    if (error instanceof TypeError) {
      throw new ApiError(
        `Pihu backend reachable nahi hai at ${API_BASE_URL}. Start FastAPI with: uvicorn api.app:app --reload --host 127.0.0.1 --port 8000`,
        { status: 0 },
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
};
