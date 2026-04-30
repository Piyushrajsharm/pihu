# 🧬 Pihu: The Autonomous AI Co‑Pilot

## Technical Project Report — April 2026

**Author:** Piyush Raj Sharma  
**Domain:** Intelligent Systems & Layered Autonomy  
**Project Status:** All Phases Implemented — Production Hardening In Progress  
**Repository:** `d:\JarvisProject\pihu`

---

> _"Pihu is not just an assistant; it is a bridge between human intent and machine execution."_

---

## 📊 Project at a Glance

| Metric | Value |
|:---|:---|
| **Total Source Files** | 69+ core files |
| **Python Backend Modules** | 45+ modules |
| **Frontend Pages** | 4 (Login, Dashboard, Chat, Predictions) |
| **SaaS API Endpoints** | 8 REST + 1 WebSocket |
| **AI Agent Types** | 7 (Chat, Search, Reasoning, Vision, UI Gen, System, Prediction) |
| **Security Layers** | 6 independent validation stages |
| **Development Period** | March 2026 — April 2026 |

---

## 🔷 1. Executive Summary

**Pihu** is an autonomous AI agent designed for real-time, low-latency interaction and complex task execution. Built on a modular, 6-layer architecture, Pihu goes beyond the traditional "chat" model by integrating **Voice, Vision, Swarm Intelligence, and System-Level Autonomy** into a unified platform.

Unlike conventional assistants that remain confined to conversational responses, Pihu bridges the gap between a user expressing a high-level goal in natural language and the system *actually executing* it — writing files, running scripts, automating browsers, analyzing data, and generating predictions — all while maintaining defense-in-depth security controls.

### Core Value Proposition

| Capability              | Description                                                   |
|:------------------------|:--------------------------------------------------------------|
| **Real-Time Responsiveness** | Targeting sub-200ms interaction latency (hardware-dependent; see Benchmarks) |
| **Layered Autonomy**        | 6-layer security & decision-making chain                    |
| **Stateful Intelligence**   | Persistent vector memory that tracks intent across sessions |
| **OS Integration**          | Direct control of host system via natural language          |
| **Swarm Predictions**       | Multi-agent consensus engine for scenario analysis (demonstration capability) |
| **SaaS Architecture**       | Multi-tenant API with billing, rate limiting, and audit     |

---

## 🔷 2. System Architecture

Pihu operates using a continuous **Sense → Understand → Plan → Execute → Validate → Respond** loop. Every input is routed through a deterministic decision engine that classifies intent and selects the optimal execution pipeline.

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: INTERACTION                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Voice    │  │ Text     │  │ Screen   │  │ Clipboard│   │
│  │ (Whisper)│  │ (CLI)    │  │ (Vision) │  │ (Copy)   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: INTELLIGENCE                                      │
│  ┌─────────────┐    ┌────────────┐    ┌─────────────────┐  │
│  │ Intent      │───>│ Decision   │───>│ Pipeline        │  │
│  │ Classifier  │    │ Router     │    │ Selection       │  │
│  └─────────────┘    └────────────┘    └─────────────────┘  │
│                                                             │
│  Supported Intents:                                         │
│  chat | realtime_query | deep_reasoning | vision_analysis   │
│  ui_generation | system_command | prediction                │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: MEMORY                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Mem0 + Qdrant Vector Store (Semantic RAG)           │   │
│  │  + Encrypted JSON Preferences (AES-256)              │   │
│  └──────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: EXECUTION PIPELINES                               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ │
│  │Local   │ │Cloud   │ │Vision  │ │System  │ │MiroFish  │ │
│  │LLM     │ │LLM     │ │Engine  │ │Control │ │Swarm     │ │
│  │(Llama) │ │(NVIDIA)│ │(docTR) │ │(PyAuto)│ │(4-Agent) │ │
│  └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘ │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: SaaS GATEWAY                                      │
│  ┌──────────┐ ┌────────┐ ┌────────┐ ┌─────────┐ ┌───────┐ │
│  │ FastAPI  │ │ JWT    │ │ Stripe │ │ Redis   │ │Celery │ │
│  │ Gateway  │ │ Auth   │ │Billing │ │ Limiter │ │Workers│ │
│  └──────────┘ └────────┘ └────────┘ └─────────┘ └───────┘ │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: SAFETY & COMPLIANCE                               │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ Semantic │ │ Governance │ │ Audit    │ │ Hash Chain  │ │
│  │ Firewall │ │ Policy Eng │ │ Trail    │ │ Integrity   │ │
│  └──────────┘ └────────────┘ └──────────┘ └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Decision Router Flow

```
User Input
    │
    ▼
┌─────────────┐      ┌──────────────────────────────────┐
│  Intent     │─────>│  Route Selection                  │
│  Classifier │      │                                    │
│  (7 types)  │      │  "search stock"  → realtime_query │
└─────────────┘      │  "explain this"  → deep_reasoning │
                     │  "open chrome"   → system_command  │
                     │  "predict trend" → prediction      │
                     │  "look at screen"→ vision_analysis │
                     │  "create a UI"   → ui_generation   │
                     │  (default)       → chat            │
                     └──────────────────────────────────┘
```

---

## 🔷 3. Complete Technology Stack

### 🎙️ Interaction Layer

| Component         | Technology                 | Role                              |
|:------------------|:---------------------------|:----------------------------------|
| Speech-to-Text    | `Faster-Whisper` (Local)   | Real-time voice transcription     |
| Text-to-Speech    | `RealtimeTTS` v2 + Kokoro  | Streaming voice synthesis         |
| Voice Activity    | `Silero VAD`               | Intelligent voice detection       |
| Audio I/O         | `sounddevice` + `PyAudio`  | Low-latency audio capture         |

### 🧠 Intelligence Layer

| Component          | Technology                    | Role                           |
|:-------------------|:------------------------------|:-------------------------------|
| Local LLM          | `llama.cpp` (GGUF Q4)        | Fast, private inferences       |
| Cloud LLM          | `NVIDIA NIM API`             | High-power reasoning           |
| Cloud LLM (Alt)    | `Groq` (Llama3)              | Ultra-fast cloud fallback      |
| Intent Classifier  | Hybrid Keyword + LLM         | 7-way intent classification    |
| Decision Router    | Deterministic Rule Engine     | Pipeline selection             |
| Critic Swarm       | Multi-Agent Validation        | Plan safety pre-checks         |

### 💾 Memory & Data Layer

| Component          | Technology                    | Role                           |
|:-------------------|:------------------------------|:-------------------------------|
| Vector Memory      | `Mem0` + `Qdrant`             | Semantic RAG storage           |
| Preferences        | JSON + AES-256 Encryption     | User settings persistence      |
| Context Engine     | Clipboard + OCR + Active App  | Real-time environment capture  |
| Task Planner       | Structured Plan Engine        | Multi-step goal management     |

### 🖥️ Execution Layer

| Component          | Technology                    | Role                           |
|:-------------------|:------------------------------|:-------------------------------|
| OS Automation      | `PyAutoGUI` + `pyttsx3`       | Mouse, keyboard, app control   |
| Browser Automation | `Selenium` + `GodMode`        | Web scraping & interactions    |
| Code Execution     | `OpenInterpreter` + `E2B`     | Sandboxed script execution     |
| Web Search         | `DuckDuckGo` API              | Real-time data retrieval       |
| Vision/OCR         | `docTR` + Cloud Vision        | Screen & image analysis        |
| MCP Dispatcher     | Model Context Protocol        | UI generation pipeline         |
| MiroFish Swarm     | 4-Agent Consensus Engine      | Predictive analysis (demo)     |
| Window Manager     | `win32gui` + `psutil`         | OS-level window control        |

### ☁️ SaaS & Infrastructure Layer

| Component          | Technology                    | Role                           |
|:-------------------|:------------------------------|:-------------------------------|
| API Gateway        | `FastAPI` + `Uvicorn`         | REST & WebSocket endpoints     |
| Authentication     | JWT (HS256) + RBAC + API Keys | Multi-tenant auth              |
| Billing            | Stripe Ledger Engine          | Token-based usage billing      |
| Rate Limiting      | Redis Sliding Window          | Per-tenant rate control        |
| Background Jobs    | Celery + Redis Broker         | Async task processing          |
| Cloud Sandbox      | E2B Containers                | Isolated code execution        |
| Container Infra    | Docker Compose                | Full-stack local deployment    |
| IaC                | Terraform                     | Cloud infrastructure planning  |

### 🛡️ Security & Compliance Layer

| Component          | Technology                    | Role                           |
|:-------------------|:------------------------------|:-------------------------------|
| Encryption at Rest | AES-256 + Fernet              | Encrypted preferences & data   |
| Secrets Manager    | Env vars → Vault abstraction  | Environment-aware key retrieval|
| Semantic Firewall  | Regex + Intent Analysis       | Prompt injection defense       |
| Audit Logging      | Hash Chain (SHA-256)          | Tamper-evident immutable logs  |
| Governance Engine  | Policy-based RBAC + deny lists| Per-tool access control        |
| Loop Prevention    | Failure Counter + Circuit Breaker | Infinite loop protection   |
| Idempotency        | Request Key Deduplication     | Duplicate request prevention   |

### 🎨 Frontend & UI Layer

| Component          | Technology                   | Role                           |
|:-------------------|:-----------------------------|:-------------------------------|
| Framework          | React 18 + Vite 8            | Modern SPA frontend            |
| Routing            | React Router DOM             | Client-side routing            |
| Design System      | Custom CSS (Glassmorphism)   | Aero-modern dark theme         |
| Fonts              | Inter + Outfit + JetBrains Mono | Typography system           |
| Animations         | CSS Keyframes + Transitions  | Micro-interactions             |

---

## 🔷 4. Key Features & Capabilities

### 🎙️ Feature 1: Low-Latency Voice Interface
- **Continuous Listening**: Silero VAD with intelligent interruption support
- **Streaming Pipeline**: Words are synthesized and spoken *while* the model is still generating text
- **Hinglish Persona**: Natural, conversational bilingual tone (English + Hindi)
- **WebSocket Voice**: Real-time audio streaming via WebSocket for remote connections
- **Latency**: Targeting sub-200ms on GPU-equipped hardware; CPU-only performance is higher (~800ms STT, ~2500ms TTS per sentence chunk per configured targets)

### 🧠 Feature 2: MiroFish Swarm Intelligence (Demonstration Capability)

> **Note:** MiroFish is a demonstration of multi-agent reasoning architecture. It is not a production-validated forecasting system and should not be used for financial or high-stakes decisions. Predictions are based on LLM reasoning heuristics, not on statistical models or real-time market data.

A multi-agent prediction engine that spawns 4 specialized "fish" agents to analyze any query from different perspectives:

| Agent | Role | Perspective |
|:---|:---|:---|
| 🔬 ResearchFish | Factual Analysis | Established trends and historical data |
| 📊 AnalystFish | Pattern Recognition | Statistical patterns and cyclical behavior |
| 🔥 ContrarianFish | Devil's Advocate | Risks, counterarguments, overlooked factors |
| 🛡️ SentinelFish | Risk Assessment | Downside risk, tail events, safety |

**Features:**
- Weighted voting → consensus prediction (Bullish / Bearish / Neutral)
- 4 scenario modes: Neutral, Bullish, Bearish, Black Swan
- No external data required — pure LLM reasoning with heuristic fallback
- Streaming output for real-time UI updates
- Full dedicated dashboard page with agent status visualization

### 🖥️ Feature 3: OS Autonomy
- **System Control**: Open/close apps, manage files, adjust volume/brightness — all via natural language
- **Vision Grounding**: OCR-based screen analysis to "see" and interact with any application
- **Web Intelligence**: Real-time search, data extraction, and web automation
- **Code Execution**: Write and run Python/JS/Shell scripts in sandboxed environments
- **Automation**: Complex multi-step workflows like "clean this CSV, visualize it, and email the report"

### 🛡️ Feature 4: Defense-in-Depth Security
- **Semantic Firewall**: Blocks prompt injection attacks using regex pattern analysis
- **Tamper-Evident Audit Trail**: Hash-chained audit logs providing compliance-aligned controls for SOC 2 readiness (full SOC 2 certification requires external audit and organizational processes beyond code)
- **RBAC Access Control**: Granular role-based access with 5 permission scopes (`read`, `write`, `execute`, `predict`, `admin`) across 5 roles (`owner`, `admin`, `member`, `service`, `viewer`)
- **Governance Policy Engine**: Configurable per-org policies with per-tool permissions, command deny lists, step-up approval thresholds, and tool rate limiting
- **Destructive Command Detection**: Blocks `rm -rf`, `DROP TABLE`, and similar operations with human-in-the-loop confirmation
- **Secrets Management**: Environment-aware key retrieval with rotation support (env vars for dev, designed for Vault/KMS integration in production)
- **AES-256 Encryption**: Fernet-based encryption for tenant preferences at rest

### ☁️ Feature 5: Multi-Tenant SaaS Architecture
A backend API designed for horizontal scalability:

| Endpoint | Method | Purpose |
|:---|:---|:---|
| `/api/v1/auth/login` | POST | JWT authentication |
| `/api/v1/chat` | POST | Main AI interaction |
| `/api/v1/predict` | POST | MiroFish swarm prediction |
| `/api/v1/health` | GET | Infrastructure health check |
| `/api/v1/billing/usage` | GET | Token quota monitoring |
| `/api/v1/audit/logs` | GET | Audit log export |
| `/api/v1/slos` | GET | SLO status & error budget |
| `/ws/stream` | WebSocket | Real-time voice/text streaming |

**Infrastructure:**
- Redis-backed rate limiting (sliding window) with graceful degradation when Redis is unavailable
- Stripe billing integration with 3 subscription tiers (`free`, `pro`, `enterprise`), overage handling, credit/refund support, and webhook lifecycle management
- Celery workers with exponential backoff, jitter, dead-letter queue, and PostgreSQL result persistence
- Stateful circuit breaker (closed → open → half-open) for LLM, database, Redis, and external APIs
- Degraded mode detection — auto-disables rate limiting when Redis is down, switches to read-only when DB is unavailable
- E2B cloud sandboxes for isolated code execution
- Docker Compose deployment with PostgreSQL, Redis, Prometheus, Grafana
- SLO tracking with error budget monitoring and Prometheus alerting rules

### 🎨 Feature 6: Aero-Modern UI
A 4-page web application with consistent dark glassmorphic design:

| Page | Purpose | Key Features |
|:---|:---|:---|
| **Login** | Authentication | Animated logo orb, gradient rings, demo mode |
| **Dashboard** | Command Center | Live metrics, usage bar, prediction widget, service health |
| **Chat** | Agent Workspace | WebSocket streaming, intent badges, mic recording |
| **Predictions** | MiroFish Swarm | Agent cards, scenario selector, consensus results, history |

---

## 🔷 5. Production Hardening (Phase 6)

This section documents the 14-point hardening effort applied after the initial build.

### Changes Implemented

| # | Area | What Changed |
|:--|:-----|:-------------|
| 1 | Multi-Tenancy | Row-level security, `tenant_filter()` / `org_filter()` helpers on all DB queries |
| 2 | Tenant Lifecycle | `tenant_manager.py`: org provisioning, member CRUD, GDPR-compliant offboarding, API key lifecycle |
| 3 | Auth Hardening | 5 permission scopes, API key auth (SHA-256 hashed), service accounts, environment-gated demo mode |
| 4 | Secrets Mgmt | `secrets.py`: abstract secrets interface, key rotation with versioning, tenant-scoped secrets, prod readiness checks |
| 5 | Governance | Policy engine rewrite: per-tool RBAC, command deny lists, domain allowlists, step-up approval, tool rate limits, blocked-action audit |
| 6 | Reliability | Celery: exponential backoff + jitter, DLQ, soft/hard timeouts, PostgreSQL result persistence |
| 7 | Resilience | Circuit breaker state machine, degraded mode detector, idempotency enforcement, retry-after headers |
| 8 | Observability | SLO definitions, error budget tracking, trace correlation IDs, per-endpoint latency histograms, model cost metrics, queue backlog gauges |
| 9 | Alerting | Prometheus alert rules: high latency, high error rate, queue backlog, token budget exhaustion, Redis down |
| 10 | Config | `PIHU_ENV` gating (`development`/`staging`/`production`), API keys from env vars only, demo mode disabled in production |
| 11 | Billing | 3 subscription tiers, soft/hard limit overage handling, failed payment tracking, credits/refunds, Stripe webhooks with signature verification |
| 12 | CI/CD | GitHub Actions pipeline: lint (ruff), type check, frontend build, dependency audit |
| 13 | Benchmarks | `benchmarks/latency_test.py`: measures p50/p95/p99 for intent classification, routing, LLM inference, and full pipeline |
| 14 | Audit Trail | Hash-chained tamper-evident logging with chain verification, honest compliance language |

---

## 🔷 6. Codebase Structure

```
pihu/
├── main.py                    # Immortal event loop — auto-restart on crash
├── pihu_brain.py              # Central orchestrator (STT→Intent→Router→Voice)
├── router.py                  # Decision engine — 7 pipeline routes
├── intent_classifier.py       # Hybrid keyword + LLM intent detection
├── config.py                  # Environment-aware configuration
├── logger.py                  # Color-coded structured logging
│
├── llm/                       # Intelligence engines
│   ├── llama_cpp_llm.py       # Local LLM (llama.cpp GGUF)
│   ├── cloud_llm.py           # NVIDIA NIM API connector
│   ├── groq_llm.py            # Groq ultra-fast fallback
│   └── local_llm.py           # Legacy local LLM wrapper
│
├── tools/                     # Execution capabilities
│   ├── automation.py          # 17KB PyAutoGUI OS automation
│   ├── mirofish_simulator.py  # Multi-agent swarm prediction engine
│   ├── vision.py              # Screen analysis pipeline
│   ├── vision_grounding.py    # OCR + spatial grounding
│   ├── web_search.py          # DuckDuckGo real-time search
│   ├── godmode_bridge.py      # Browser automation (GodMode)
│   ├── mcp_dispatcher.py      # UI generation via MCP
│   ├── window_manager.py      # Window management (win32gui)
│   └── pencil_swarm_agent.py  # Autonomous planning agent
│
├── api/                       # SaaS backend (15 modules)
│   ├── app.py                 # FastAPI gateway (8 endpoints + WebSocket)
│   ├── auth.py                # JWT + RBAC + API key authentication
│   ├── tenant_manager.py      # Org lifecycle, member CRUD, API keys
│   ├── secrets.py             # Environment-aware secrets management
│   ├── billing.py             # Stripe billing with 3 tiers
│   ├── database.py            # Async PostgreSQL + row-level security
│   ├── rate_limiter.py        # Redis sliding-window limiter
│   ├── firewall.py            # Semantic prompt injection filter
│   ├── governance.py          # Policy engine (per-tool RBAC, deny lists)
│   ├── middleware.py          # Circuit breaker, idempotency, degraded mode
│   ├── observability.py       # SLOs, error budgets, Prometheus metrics
│   ├── telemetry.py           # Hash-chained tamper-evident audit logger
│   ├── worker.py              # Celery: backoff, DLQ, timeouts
│   ├── sandbox_executor.py    # E2B cloud sandbox
│   └── swarm_coordinator.py   # Distributed task coordinator
│
├── frontend/src/              # React + Vite frontend
│   ├── App.jsx                # Router with protected routes
│   ├── index.css              # Complete design system
│   └── pages/
│       ├── Login.jsx + Login.css
│       ├── Dashboard.jsx + Dashboard.css
│       ├── Chat.jsx
│       └── Predictions.jsx + Predictions.css
│
├── security/
│   └── security_core.py       # AES-256, DPAPI, hash chain logging
│
├── benchmarks/
│   └── latency_test.py        # P50/P95/P99 latency measurement
│
├── infra/
│   ├── alerts.yml             # Prometheus alerting rules
│   └── prometheus.yml         # Prometheus scrape config
│
├── .github/workflows/
│   └── ci.yml                 # CI/CD pipeline (lint, build, audit)
│
├── memory_engine.py           # Mem0 + Qdrant vector memory
├── streaming_pipeline.py      # Token-by-token voice streaming
├── stt_engine.py              # Faster-Whisper speech recognition
├── tts_engine.py              # RealtimeTTS voice synthesis
├── audio_io.py                # Low-latency audio I/O
├── scheduler.py               # Cron-like task scheduler
├── critic_swarm.py            # Multi-agent safety validation
├── context_rag_engine.py      # Contextual RAG pipeline
├── planner_engine.py          # Multi-step task planner
├── interpreter_engine.py      # OpenInterpreter code execution
├── openclaw_bridge.py         # OpenClaw messaging bridge
│
├── docker-compose.yml         # Full-stack deployment
├── Dockerfile.backend         # Backend container
├── requirements.txt           # Python dependencies
└── ARCHITECTURE_WHITEPAPER.md # Technical whitepaper
```

---

## 🔷 7. Development Roadmap

| Phase | Description | Status | Key Deliverables |
|:---|:---|:---|:---|
| **Phase 1** | Local Foundations | ✅ Complete | STT/TTS, local LLM, voice interface, OS automation |
| **Phase 2** | Hybrid Scaling | ✅ Complete | Cloud LLM integration, multi-agent critic swarm, web search |
| **Phase 3** | SaaS Readiness | ✅ Complete | FastAPI gateway, JWT auth, Stripe billing, health checks, rate limiting |
| **Phase 4** | Swarm Intelligence | ✅ Complete | MiroFish 4-agent prediction engine, streaming results, router integration |
| **Phase 5** | Native UI | ✅ Complete | Premium React frontend (4 pages), glassmorphic design, live metrics |
| **Phase 6** | Production Hardening | ✅ Implemented | Multi-tenancy, secrets, governance, reliability, observability, CI/CD |

---

## 🔷 8. How It Works — End-to-End Example

### Example: User says "Predict if AI will replace developers"

```
Step 1: STT Engine transcribes voice → "Predict if AI will replace developers"
Step 2: Intent Classifier matches "predict" keyword → type = "prediction" (90%)
Step 3: Router selects _route_prediction pipeline
Step 4: Auto-detects scenario = "neutral"
Step 5: MiroFish spawns 4 agents:
        🔬 ResearchFish: "Historical trends suggest augmentation, not replacement" → NEUTRAL
        📊 AnalystFish: "Productivity tools adoption cyclical" → BULLISH
        🔥 ContrarianFish: "Code generation capability growing faster than expected" → BEARISH
        🛡️ SentinelFish: "Regulatory and quality concerns limit automation" → NEUTRAL
Step 6: Weighted consensus → NEUTRAL (67% confidence)
Step 7: Result streamed to TTS → Pihu speaks the prediction
Step 8: Audit log recorded with hash chain entry
```

---

## 🔷 9. Deployment & Infrastructure

### Local Development
```bash
# Start the backend
uvicorn api.app:app --reload --port 8000

# Start the frontend
cd frontend && npm run dev

# Start the voice agent
python main.py
```

### Docker Deployment
```bash
docker-compose up -d
# Starts: PostgreSQL, Redis, Backend, Celery Worker, Prometheus, Grafana
```

### Service Ports
| Service | Port | Purpose |
|:---|:---|:---|
| FastAPI Gateway | 8000 | REST + WebSocket API |
| Vite Frontend | 5173 | React development server |
| PostgreSQL | 5432 | Relational database |
| Redis | 6379 | Rate limiting + job broker |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Monitoring dashboard |

---

## 🔷 10. Key Design Decisions

| Decision | Rationale |
|:---|:---|
| **Hybrid LLM (Local + Cloud)** | Local for speed & privacy, cloud for power — automatic fallback |
| **Deterministic Router** | Predictable behavior vs. LLM-based routing — safer and faster |
| **Semantic Firewall** | Prevents prompt injection at the API boundary before reaching LLM |
| **Hash Chain Logging** | Tamper-evident audit trail for compliance-aligned auditing |
| **No CSV Required for MiroFish** | Pure reasoning with heuristic fallback — data is optional enhancement |
| **Demo Mode Auth** | Environment-gated: allows instant access in dev, fully disabled in production |
| **Glassmorphic UI** | Premium, modern aesthetic that differentiates from generic dashboards |
| **Row-Level Security** | Tenant isolation enforced at the data layer, not just the API layer |
| **Per-Tool Governance** | Granular access control prevents role escalation through tool misuse |

---

## 🔷 11. Known Limitations

This section provides an honest assessment of current limitations and areas requiring further work before production deployment.

| Area | Limitation | Mitigation Path |
|:---|:---|:---|
| **Auth** | JWT uses HS256 with a shared secret; no OAuth/OIDC flow | Integrate Supabase/Clerk for production auth |
| **Database** | Row-level security is enforced in application code, not via PostgreSQL RLS policies | Add native PG RLS for defense-in-depth |
| **Secrets** | Production secrets interface is defined but not yet connected to Vault/KMS | Deploy with HashiCorp Vault or AWS Secrets Manager |
| **Rate Limiting** | In-memory fallback when Redis is down has no persistence across restarts | Acceptable for graceful degradation; monitor Redis uptime |
| **Billing** | Stripe integration is structurally complete but not end-to-end tested with live Stripe account | Requires staging environment with Stripe test mode |
| **MiroFish** | Not a validated forecasting tool; predictions are based on LLM heuristics | Position as demonstration capability only |
| **Testing** | No automated unit or integration test suite beyond import verification | Build test suite as next priority |
| **Session Store** | Sessions are in-memory; horizontal scaling requires Redis session store | Implement Redis-backed sessions |
| **Observability** | Metrics collected but no pre-built Grafana dashboards shipped | Create dashboard provisioning configs |
| **TTS Quality** | CPU-only TTS latency (~2.5s/sentence) exceeds real-time targets on low-end hardware | GPU acceleration recommended for production voice use |

---

## 🔷 12. Production Readiness Checklist

| Category | Item | Status |
|:---|:---|:---|
| **Security** | JWT authentication | ✅ Implemented |
| | Granular RBAC (5 scopes × 5 roles) | ✅ Implemented |
| | API key auth (hashed, expirable) | ✅ Implemented |
| | Demo mode disabled in production | ✅ Implemented |
| | Secrets loaded from env vars (not hardcoded) | ✅ Implemented |
| | Vault/KMS integration | ⬜ Designed, not deployed |
| | OAuth/OIDC support | ⬜ Not implemented |
| **Data** | Tenant data isolation | ✅ Application-level RLS |
| | Database-level RLS (PG policies) | ⬜ Not implemented |
| | AES-256 encryption at rest | ✅ Implemented |
| | GDPR offboarding/data purge | ✅ Implemented |
| **Reliability** | Circuit breaker | ✅ Implemented |
| | Graceful degradation | ✅ Implemented |
| | Dead-letter queue | ✅ Implemented |
| | Idempotency enforcement | ✅ Implemented |
| | Automated failover | ⬜ Requires infrastructure |
| **Observability** | Prometheus metrics | ✅ Implemented |
| | SLO tracking with error budgets | ✅ Implemented |
| | Trace correlation IDs | ✅ Implemented |
| | Alerting rules | ✅ Defined |
| | Grafana dashboards | ⬜ Not provisioned |
| **Billing** | Subscription tiers | ✅ Implemented |
| | Overage handling | ✅ Implemented |
| | Stripe webhooks | ✅ Implemented |
| | Live Stripe testing | ⬜ Requires staging |
| **Testing** | Import verification | ✅ CI pipeline |
| | Unit tests | ⬜ Not implemented |
| | Integration tests | ⬜ Not implemented |
| | Load testing | ⬜ Not performed |
| **Deployment** | Docker Compose | ✅ Defined |
| | CI/CD pipeline | ✅ GitHub Actions |
| | Kubernetes manifests | ⬜ Not implemented |
| | Terraform IaC | ✅ Defined |

---

## 🔷 13. Maturity Assessment

| Dimension | Level | Notes |
|:---|:---|:---|
| **Architecture** | 🟢 Strong | Clean 6-layer separation, well-defined interfaces |
| **Security** | 🟡 Good | Defense-in-depth present; needs OAuth, PG-RLS, Vault for production |
| **Reliability** | 🟡 Good | Circuit breaker, DLQ, degraded mode in place; needs chaos testing |
| **Observability** | 🟡 Good | Metrics, SLOs, trace IDs defined; dashboards not yet provisioned |
| **Testing** | 🔴 Gaps | No automated test suite; highest priority next investment |
| **Billing** | 🟡 Good | Full lifecycle coded; needs live Stripe integration testing |
| **Frontend** | 🟢 Strong | Production-quality UI; needs mobile responsiveness pass |
| **Documentation** | 🟢 Strong | Architecture whitepaper, this report, inline docstrings |

---

## 🔷 14. Future Enhancements (Post-V1)

| Enhancement | Priority | Description |
|:---|:---|:---|
| Automated Test Suite | **Critical** | pytest unit + integration tests for all API modules |
| Redis Session Store | High | Replace in-memory sessions for horizontal scaling |
| PostgreSQL RLS | High | Native database-level row isolation policies |
| Stripe Live Testing | High | End-to-end billing validation in staging environment |
| Grafana Dashboards | Medium | Pre-built monitoring dashboards for key SLOs |
| Supabase/Clerk Auth | Medium | Production OAuth with social login support |
| Tauri Desktop Wrapper | Medium | Cross-platform native desktop application |
| Kubernetes Manifests | Medium | Production container orchestration |
| Real-time Charts | Low | D3.js/Recharts visualizations on Dashboard |
| Mobile Responsive | Low | Full mobile optimization for all pages |
| Plugin Marketplace | Low | User-installable skill extensions |

---

> [!TIP]
> **Performance**: When running locally, ensure GPU acceleration for `faster-whisper` and `llama.cpp` to approach the sub-200ms latency target. CPU-only performance is functional but significantly slower.

> [!IMPORTANT]
> **Safety First**: Pihu's safety layer is non-bypassable. All high-risk system commands require explicit human-in-the-loop confirmation. Demo mode is fully disabled in production (`PIHU_ENV=production`).

> [!NOTE]
> **Open Source Components**: Pihu integrates 15+ open-source frameworks to deliver its capabilities. See `requirements.txt` for the full dependency list.

> [!WARNING]
> **MiroFish Disclaimer**: The swarm prediction engine is a demonstration of multi-agent architecture. It is not a validated forecasting tool and must not be used for financial, medical, or other high-stakes decisions.

---

**Prepared by:** Piyush Raj Sharma  
**Architecture Consulting:** Antigravity AI  
**Date:** April 26, 2026  
**Version:** 3.0 (Production Hardening Complete)
