import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { WS_BASE_URL, createRequestId, DEMO_TOKEN, fetchJson, getStoredToken } from '../api';
import '../index.css';

const PERSONA_MODES = [
  {
    id: 'saheli',
    label: 'Saheli',
    subtitle: 'Warm, playful, caring',
    hint: 'Reply in warm Hinglish with a friendly companion tone. Keep it playful, respectful, and useful.',
  },
  {
    id: 'focus',
    label: 'Focus',
    subtitle: 'Sharp, practical, calm',
    hint: 'Reply in clear Hinglish with a focused engineering tone. Be concise, direct, and still friendly.',
  },
  {
    id: 'masti',
    label: 'Masti',
    subtitle: 'Playful, witty, bright',
    hint: 'Reply in playful Hinglish with quick charm and wit. Keep it respectful and never explicit.',
  },
  {
    id: 'sherni',
    label: 'Sherni',
    subtitle: 'Bold, confident, hype',
    hint: 'Reply in confident Hinglish with upbeat encouragement. Be bold, crisp, and supportive.',
  },
];

const QUICK_PROMPTS = [
  'Plan my next 3 steps',
  'Debug this with me',
  'Make this sound charming',
  'Explain it simply',
];

const pihuAvatar = '/pihu-avatar.webp';

const makeMessageId = () => createRequestId();

const buildLocalFallbackReply = (text, persona) => {
  const normalized = text.toLowerCase().trim();
  if (normalized.includes('free') || normalized.includes('billing') || normalized.includes('subscription')) {
    return 'Haan, local Pihu free mode me hai. Billing ka tension nahi, bas app ko fast aur useful rakhte hain.';
  }
  if (normalized.includes('code') || normalized.includes('debug') || normalized.includes('error')) {
    return 'Backend slow hua, but main tumhe stuck nahi chhodungi. Error/code paste karke thoda chhota chunk bhejo, main fast path se debug start kar dungi.';
  }
  if (normalized.endsWith('?')) {
    return `Fast fallback: mujhe backend se reply time pe nahi mila. ${persona.label} mode me short answer chahiye to sawal ko ek line me bhejo, main turant pakadti hoon.`;
  }
  return `Main abhi local fallback se reply kar rahi hoon, ${persona.label} mode on hai. Backend slow ho gaya tha, par main yahin hoon, bolo kya next?`;
};

const SendIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

const MicIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </svg>
);

const DashboardIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <rect x="3" y="3" width="7" height="7" />
    <rect x="14" y="3" width="7" height="7" />
    <rect x="14" y="14" width="7" height="7" />
    <rect x="3" y="14" width="7" height="7" />
  </svg>
);

const ChatIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const PulseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
);

const SparkIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" />
    <path d="M18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8L18 16z" />
  </svg>
);

const Chat = () => {
  const navigate = useNavigate();
  const [personaMode, setPersonaMode] = useState('saheli');
  const [messages, setMessages] = useState([
    {
      id: makeMessageId(),
      role: 'ai',
      text: 'Hi Piyush, Pihu desktop pe ready hai. Drop a thought, bug, plan, or voice note and I will stay right beside it.',
      intent: 'system_ready',
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [wsStatus, setWsStatus] = useState('disconnected');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const messagesEndRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const shouldReconnectRef = useRef(true);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);

  const token = getStoredToken() || DEMO_TOKEN;
  const selectedPersona = useMemo(
    () => PERSONA_MODES.find((mode) => mode.id === personaMode) || PERSONA_MODES[0],
    [personaMode],
  );
  const latestAiMessage = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'ai') || messages[0],
    [messages],
  );

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const stopMediaTracks = useCallback(() => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }, []);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    } else {
      stopMediaTracks();
      setIsRecording(false);
    }
  }, [stopMediaTracks]);

  const appendStreamChunk = useCallback((chunk) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last?.role === 'ai' && last?.streaming) {
        return [...prev.slice(0, -1), { ...last, text: `${last.text}${chunk}` }];
      }
      return [...prev, { id: makeMessageId(), role: 'ai', text: chunk, streaming: true }];
    });
  }, []);

  const finishStream = useCallback((data) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last?.streaming) {
        return [
          ...prev.slice(0, -1),
          {
            ...last,
            text: last.text || data.full_response || 'Done.',
            streaming: false,
            intent: data.intent || last.intent,
          },
        ];
      }

      if (data.full_response) {
        return [...prev, {
          id: makeMessageId(),
          role: 'ai',
          text: data.full_response,
          intent: data.intent,
        }];
      }

      return prev;
    });
    setIsLoading(false);
  }, []);

  useEffect(() => {
    shouldReconnectRef.current = true;

    const scheduleReconnect = () => {
      if (!shouldReconnectRef.current) return;
      reconnectTimerRef.current = window.setTimeout(connectWs, 3000);
    };

    const connectWs = () => {
      if (!shouldReconnectRef.current) return;

      try {
        setWsStatus('connecting');
        const socket = new WebSocket(`${WS_BASE_URL}/ws/stream`);
        wsRef.current = socket;

        socket.onopen = () => {
          setWsStatus('connected');
          socket.send(JSON.stringify({ token, tone: personaMode }));
        };

        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'stream') {
              appendStreamChunk(data.chunk || '');
              return;
            }
            if (data.type === 'done') {
              finishStream(data);
              return;
            }
            if (data.type === 'error') {
              setMessages((prev) => [...prev, {
                id: makeMessageId(),
                role: 'ai',
                text: data.message || 'Connection me thoda issue aa gaya. Ek baar phir try karte hain.',
                intent: 'ws_error',
              }]);
              setIsLoading(false);
            }
          } catch {
            // Audio acknowledgements and malformed packets are intentionally ignored.
          }
        };

        socket.onclose = () => {
          if (!shouldReconnectRef.current) return;
          setWsStatus('disconnected');
          scheduleReconnect();
        };

        socket.onerror = () => {
          setWsStatus('error');
          socket.close();
        };
      } catch {
        setWsStatus('error');
        scheduleReconnect();
      }
    };

    connectWs();

    return () => {
      shouldReconnectRef.current = false;
      window.clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      stopRecording();
    };
  }, [appendStreamChunk, finishStream, personaMode, stopRecording, token]);

  const toggleRecording = async () => {
    if (isRecording) {
      stopRecording();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setMessages((prev) => [...prev, {
        id: makeMessageId(),
        role: 'ai',
        text: 'Mic support browser me available nahi hai. Text bhej do, main yahin hoon.',
        intent: 'mic_unavailable',
      }]);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const recorderOptions = window.MediaRecorder?.isTypeSupported?.('audio/webm')
        ? { mimeType: 'audio/webm' }
        : undefined;
      const mediaRecorder = new MediaRecorder(stream, recorderOptions);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        stopMediaTracks();
        setIsRecording(false);
      };

      mediaRecorder.start(250);
      setIsRecording(true);
    } catch (error) {
      setMessages((prev) => [...prev, {
        id: makeMessageId(),
        role: 'ai',
        text: `Mic access nahi mila. Browser permissions check kar lo, phir main sun lungi. (${error.message})`,
        intent: 'mic_blocked',
      }]);
    }
  };

  const handleSend = async (event, presetText) => {
    event?.preventDefault();
    const text = (presetText ?? input).trim();
    if (!text || isLoading) return;

    const userMessage = { id: makeMessageId(), role: 'user', text };
    setMessages((prev) => [...prev, userMessage]);
    if (!presetText) setInput('');
    setIsLoading(true);

    try {
      const data = await fetchJson('/api/v1/chat', {
        method: 'POST',
        token,
        timeoutMs: 45000,
        headers: { 'X-Idempotency-Key': createRequestId() },
        body: {
          message: userMessage.text,
          tone: personaMode,
        },
      });

      setMessages((prev) => [...prev, {
        id: makeMessageId(),
        role: 'ai',
        text: data.response || 'Mujhe response blank mila, but main yahin hoon. Ek baar aur try karein?',
        intent: data.intent_detected,
        latency: data.latency_ms,
      }]);
    } catch (error) {
      const message = error.status === 0
        ? `Backend se connection nahi ban paaya, but app free fallback pe alive hai.\n${error.message || 'Start FastAPI on port 8000.'}`
        : buildLocalFallbackReply(userMessage.text, selectedPersona);

      setMessages((prev) => [...prev, {
        id: makeMessageId(),
        role: 'ai',
        text: message,
        intent: error.status === 0 ? 'offline_fallback' : 'local_fast_fallback',
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDesktopPointerMove = useCallback((event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - 0.5).toFixed(3);
    const y = ((event.clientY - rect.top) / rect.height - 0.5).toFixed(3);
    event.currentTarget.style.setProperty('--mouse-x', x);
    event.currentTarget.style.setProperty('--mouse-y', y);
  }, []);

  return (
    <div className="desktop-mate-app mate-shell" onPointerMove={handleDesktopPointerMove}>
      <div className="mate-desktop" aria-hidden="true">
        <div className="mate-window mate-window-large">
          <div className="mate-window-bar"><span /><span /><span /></div>
          <div className="mate-window-lines">
            <i /><i /><i /><i />
          </div>
        </div>
        <div className="mate-window mate-window-small">
          <div className="mate-window-bar"><span /><span /><span /></div>
          <strong>Active focus</strong>
          <p>1 gentle nudge waiting</p>
        </div>
        <div className="mate-taskbar">
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>

      <div className="mate-status-chip">
        <span className="mate-brand-mark">P</span>
        <strong>Pihu</strong>
        <i className={`status-dot ${wsStatus}`} />
      </div>

      <main className="mate-floating-stage">
        <section className={`mate-presence ${isRecording ? 'is-listening' : ''}`} aria-label="Pihu desktop companion">
          <div className="mate-bubble">
            <span>{selectedPersona.label}</span>
            {isLoading ? (
              <div className="typing-indicator" aria-label="Pihu is typing">
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
            ) : (
              <p>{isRecording ? 'Bol do, main sun rahi hoon.' : latestAiMessage?.text}</p>
            )}
          </div>

          <div className="mate-cutout">
            <img src={pihuAvatar} alt="Pihu desktop companion avatar" className="mate-avatar" />
          </div>

          <div className="mate-perch">
            <span className="avatar-status-light" />
            {isRecording ? 'Listening' : wsStatus === 'connected' ? 'Sitting on desktop' : 'Reconnecting'}
          </div>

          <form className="mate-floating-input" onSubmit={handleSend}>
            <button
              type="button"
              className={`btn-mic ${isRecording ? 'recording-active' : ''}`}
              onClick={toggleRecording}
              title={isRecording ? 'Stop voice input' : 'Start voice input'}
            >
              {isRecording ? <span className="recording-dot" /> : <MicIcon />}
            </button>
            <input
              type="text"
              className="chat-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={isRecording ? 'Listening...' : `Ask Pihu in ${selectedPersona.label} mode`}
              disabled={isLoading || isRecording}
              autoFocus
            />
            <button type="submit" className="btn-send" disabled={!input.trim() || isLoading}>
              <SendIcon />
            </button>
          </form>

          <div className="mate-orbit-actions" aria-label="Quick prompts">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={(event) => handleSend(event, prompt)}
                disabled={isLoading}
              >
                {prompt}
              </button>
            ))}
          </div>
        </section>
      </main>

      <aside className={`mate-drawer glass ${isDrawerOpen ? 'open' : ''}`} aria-label="Pihu drawer">
        <div className="mate-drawer-header">
          <div>
            <span className="header-kicker">Companion Drawer</span>
            <h2>Talk With Pihu</h2>
          </div>
          <button type="button" className="btn-icon" onClick={() => setIsDrawerOpen(false)} title="Close drawer">
            ×
          </button>
        </div>

        <div className="mode-grid mate-mode-grid" role="list" aria-label="Persona tone">
          {PERSONA_MODES.map((mode) => (
            <button
              key={mode.id}
              type="button"
              className={`mode-chip ${personaMode === mode.id ? 'selected' : ''}`}
              onClick={() => setPersonaMode(mode.id)}
              title={mode.hint}
            >
              <span>{mode.label}</span>
              <small>{mode.subtitle}</small>
            </button>
          ))}
        </div>

        <div className="chat-history mate-chat-history">
          {messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.role} ${msg.streaming ? 'streaming' : ''}`}>
              <div className="message-header">
                {msg.role === 'ai' ? 'Pihu' : 'You'}
              </div>
              <div className="message-content">{msg.text}</div>
            </div>
          ))}

          {isLoading && (
            <div className="message ai loading-message">
              <div className="message-header">Pihu</div>
              <div className="typing-indicator" aria-label="Pihu is typing">
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </aside>

      <nav className="mate-pocket-dock" aria-label="Companion navigation">
        <button type="button" onClick={() => navigate('/dashboard')} title="Open control center">
          <DashboardIcon />
        </button>
        <button
          type="button"
          className={isDrawerOpen ? 'active' : ''}
          onClick={() => setIsDrawerOpen(true)}
          title="Open chat drawer"
        >
          <ChatIcon />
        </button>
        <button type="button" onClick={() => navigate('/predictions')} title="Open predictions">
          <PulseIcon />
        </button>
        <button type="button" onClick={toggleRecording} className={isRecording ? 'active' : ''} title={isRecording ? 'Stop voice input' : 'Start voice input'}>
          <MicIcon />
        </button>
      </nav>
    </div>
  );
};

export default Chat;
