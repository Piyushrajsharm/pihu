"""
Pihu SaaS Gateway — FastAPI Backend
Provides REST & WebSocket endpoints for remote, multi-tenant interactions.
"""

import os
import sys
import json
import asyncio
import logging
import time
import hashlib
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict

# Add parent directory to path so we can import completely from Pihu core
sys.path.insert(0, str(Path(__file__).parent.parent))

from pihu_brain import PihuBrain
from intent_classifier import Intent
from api.auth import verify_jwt_token, require_admin, handle_login
from api.rate_limiter import rate_limiter
from api.billing import billing_engine
from api.database import AsyncSessionLocal, init_db
from api.firewall import firewall
from api.telemetry import audit_logger
from api.observability import record_chat_metrics, instrument_app
from api.governance import governance_engine
from api.middleware import reliability_engine

app = FastAPI(
    title="Pihu SaaS Gateway",
    version="2.0.0",
    description="Multi-tenant API for the Pihu Autonomous Agent"
)

def _allowed_cors_origins() -> list[str]:
    configured = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
    )
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if os.getenv("PIHU_ENV") == "production" and "*" in origins:
        raise RuntimeError("CORS_ALLOWED_ORIGINS cannot contain '*' in production")
    return origins


# CORS config to allow the web UI without wildcard credentials.
allowed_cors_origins = _allowed_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_cors_origins,
    allow_credentials="*" not in allowed_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("API_GATEWAY")
logging.basicConfig(level=logging.INFO)

FREE_MODE_ENABLED = os.getenv("PIHU_FREE_MODE", "1").strip().lower() in {"1", "true", "yes", "on"}
FAST_CHAT_ENABLED = os.getenv("PIHU_FAST_CHAT_MODE", "1").strip().lower() in {"1", "true", "yes", "on"}
FAST_CHAT_COUNTS: Dict[str, int] = {}

# Wire OpenTelemetry + Prometheus
instrument_app(app)

# ==========================================
# STARTUP EVENT — Auto-Initialize Database
# ==========================================
@app.on_event("startup")
async def startup_event():
    """Initialize database tables and run health checks on boot."""
    try:
        await init_db()
        logger.info("✅ Database tables initialized successfully.")
    except Exception as e:
        logger.warning(f"⚠️ Database init skipped (will retry on first request): {e}")

# ==========================================
# 1. HEALTH CHECK ENDPOINT
# ==========================================
@app.get("/api/v1/health")
async def health_check():
    """Infrastructure health check — used by Docker, K8s, and frontend."""
    if FREE_MODE_ENABLED:
        return {
            "status": "healthy",
            "version": "2.0.0",
            "timestamp": time.time(),
            "mode": "free",
            "services": {
                "api": "connected",
                "billing": "disabled_free_mode",
                "quota": "unlimited",
            },
        }

    checks = {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": time.time(),
        "services": {}
    }

    # Check Redis
    try:
        if rate_limiter.redis:
            await rate_limiter.redis.ping()
            checks["services"]["redis"] = "connected"
        else:
            checks["services"]["redis"] = "not configured"
    except Exception:
        checks["services"]["redis"] = "disconnected"

    # Check PostgreSQL
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["services"]["postgres"] = "connected"
    except Exception:
        checks["services"]["postgres"] = "disconnected"

    # Check Celery
    try:
        from api.worker import celery_app
        i = celery_app.control.inspect()
        checks["services"]["celery"] = "connected" if i.ping() else "disconnected"
    except Exception:
        checks["services"]["celery"] = "disconnected"

    return checks

# ==========================================
# 2. AUTH ENDPOINTS
# ==========================================
class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=1024)

class LoginResponse(BaseModel):
    token: str
    tenant_id: str
    role: str

@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login_endpoint(request: LoginRequest):
    """
    Authenticates a user and returns a JWT token.
    Credentials are validated by api.auth.handle_login.
    """
    auth_result = await handle_login(request.email, request.password)
    tenant_id = auth_result["tenant_id"]

    audit_logger.log_event(tenant_id, "login", {
        "email": request.email,
        "status": "success"
    })

    return LoginResponse(
        token=auth_result["token"],
        tenant_id=tenant_id,
        role=auth_result["role"],
    )

# ==========================================
# 3. ENTERPRISE AUDIT ENDPOINTS (RBAC PROTECTED)
# ==========================================
@app.get("/api/v1/audit/logs", dependencies=[Depends(require_admin)])
async def get_audit_logs():
    """Only admins can view the SOC 2 immutable audit logs."""
    from api.telemetry import AUDIT_LOG_FILE
    if os.path.exists(AUDIT_LOG_FILE):
        with open(AUDIT_LOG_FILE, "r") as f:
            return [json.loads(line) for line in f.readlines() if line.strip()]
    return []

# ==========================================
# 4. STATE MANAGEMENT (MULTI-TENANT)
# ==========================================
active_sessions: Dict[str, PihuBrain] = {}

def get_brain_for_user(user_id: str) -> PihuBrain:
    """Retrieves or initializes an isolated PihuBrain for the user."""
    if user_id not in active_sessions:
        logger.info(f"Initializing new PihuBrain session for user: {user_id}")
        brain = PihuBrain(backend_mode=True, user_id=user_id)
        brain.initialize()
        active_sessions[user_id] = brain
    return active_sessions[user_id]


async def enforce_request_controls(
    *,
    user_id: str,
    role: str,
    message: str,
    tool_name: str,
    estimated_cost: int = 100,
):
    """Apply shared safety, governance, rate-limit, and billing controls."""
    firewall.inspect(message)
    governance_engine.full_check(
        tenant_id=user_id,
        role=role or "member",
        tool_name=tool_name,
        command=message,
        estimated_cost=0 if FREE_MODE_ENABLED else estimated_cost,
        org_id="org_default",
    )
    if FREE_MODE_ENABLED:
        return

    await rate_limiter.check_rate_limit(user_id)
    async with AsyncSessionLocal() as db:
        await billing_engine.verify_funding(
            tenant_id=user_id,
            org_id="org_default",
            db=db,
        )


def classify_chat_intent(brain: PihuBrain, message: str, user_id: str) -> Intent:
    """Classify chat input with the same brain path used by desktop mode."""
    try:
        classifier = getattr(brain, "intent_classifier", None)
        if classifier:
            intent = classifier.classify(message)
        else:
            intent = Intent(type="chat", confidence=0.5, metadata={}, raw_input=message)
    except Exception as e:
        logger.error("Intent classification failed; defaulting to chat: %s", e)
        intent = Intent(type="chat", confidence=0.5, metadata={}, raw_input=message)

    metadata = dict(intent.metadata or {})
    metadata["user_id"] = user_id
    return Intent(
        type=intent.type,
        confidence=intent.confidence,
        metadata=metadata,
        raw_input=intent.raw_input,
    )


ALLOWED_CHAT_TONES = {"saheli", "focus", "masti", "sherni"}


def normalize_chat_tone(tone: Optional[str]) -> str:
    """Normalize optional UI tone controls to a safe server-side allowlist."""
    normalized = (tone or "saheli").strip().lower()
    return normalized if normalized in ALLOWED_CHAT_TONES else "saheli"


def attach_chat_tone(intent: Intent, tone: Optional[str]) -> Intent:
    """Attach persona tone metadata without changing the user's actual text."""
    metadata = dict(intent.metadata or {})
    metadata["tone"] = normalize_chat_tone(tone)
    return Intent(
        type=intent.type,
        confidence=intent.confidence,
        metadata=metadata,
        raw_input=intent.raw_input,
    )


def fast_free_chat_response(message: str, tone: Optional[str] = "saheli") -> Optional[str]:
    """Instant local replies for casual chat so free mode never feels frozen."""
    if not FAST_CHAT_ENABLED:
        return None

    text = " ".join((message or "").lower().strip().split())
    if not text or len(text) > 280:
        return None

    normalized_text = text.strip(" ?!.")
    words = set(normalized_text.split())

    name_phrases = {
        "your name", "what is your name", "whats your name", "name kya hai",
        "tumhara name kya hai", "tumhara naam kya hai", "tera naam kya hai",
        "aapka naam kya hai", "tumhara name", "tumhara naam",
    }
    if normalized_text in name_phrases or (
        ("name" in words or "naam" in words) and any(word in words for word in ["your", "tumhara", "tera", "aapka"])
    ):
        return (
            "Mera naam Pihu hai. Main tumhari desktop companion hoon - chat, planning, debugging, "
            "simple explanations aur quick help ke liye yahin hoon."
        )

    who_phrases = {
        "who are you", "who r u", "who you are", "tum kaun ho", "tum kon ho",
        "tu kaun hai", "tu kon hai", "tun kon ho", "aap kaun ho", "kaun ho",
        "kon ho", "tum kya ho",
    }
    if normalized_text in who_phrases or (
        any(word in words for word in ["who", "kaun", "kon"]) and any(word in words for word in ["you", "tum", "tu", "tun", "aap"])
    ):
        return (
            "Main Pihu hoon - tumhari local AI desktop companion. Main normal baat bhi kar sakti hoon, "
            "aur jab tum code, plan, ya kisi idea pe stuck ho to saath me kaam bhi kar sakti hoon."
        )

    if any(phrase in normalized_text for phrase in ["kya kar sakti", "what can you do", "what do you do", "help me with"]):
        return (
            "Main chat, code debugging, planning, short explanations, wording polish, aur quick predictions me help kar sakti hoon. "
            "Bas task ya question seedha bhejo."
        )

    starter_prompts = {
        "plan my next 3 steps": (
            "Bilkul. Goal bhejo, phir main 3 sharp steps bana dungi. "
            "Agar abhi generic plan chahiye: 1) outcome clear karo, 2) blocker pakdo, 3) smallest next action execute karo."
        ),
        "debug this with me": (
            "Haan, chalo debug karte hain. Error message, relevant code block, aur tumne last kya change kiya tha paste karo. "
            "Main pehle failure point isolate karungi, phir fix."
        ),
        "make this sound charming": (
            "Paste the line. Main usko warm, natural, aur thoda charming bana dungi without overdoing it."
        ),
        "explain it simply": (
            "Send me the topic or paragraph. Main usko simple words, tiny steps, aur ek quick example me tod dungi."
        ),
    }
    if text in starter_prompts:
        return starter_prompts[text]
    if len(text.split()) <= 10 and any(marker in text for marker in ["debug", "error", "traceback"]):
        return (
            "Debug mode ready. Error text, expected behavior, actual behavior, aur smallest code snippet bhejo. "
            "Main direct root cause pe jaungi."
        )
    if len(text.split()) <= 10 and any(marker in text for marker in ["explain", "simplify"]):
        return "Haan, send the thing. Main usko plain language me, short steps ke saath explain kar dungi."
    if len(text.split()) <= 10 and any(marker in text for marker in ["code", "implement"]):
        return "Code path ready. Requirement aur current file/function paste karo, phir main exact implementation bataungi."

    # Keep real work on the proper router path.
    heavy_markers = {
        "code", "debug", "error", "traceback", "implement", "analyze", "explain",
        "compare", "research", "latest", "news", "price", "stock", "predict",
        "forecast", "screen", "image", "file", "run", "execute", "open ",
    }
    if any(marker in text for marker in heavy_markers):
        return None

    tone_name = normalize_chat_tone(tone)
    playful_suffix = {
        "saheli": "Bolo jaan, kya karna hai?",
        "focus": "Bolo, main seedha point pe aati hoon.",
        "masti": "Bolo, kya scene banayein?",
        "sherni": "Bolo, kaam ko pakad ke khatam karte hain.",
    }.get(tone_name, "Bolo jaan, kya karna hai?")

    greetings = {"hi", "hello", "hey", "hii", "helo", "namaste", "gm", "good morning", "good evening"}
    thanks = {"thanks", "thank you", "thx", "shukriya", "dhanyawad"}

    if text in greetings or text.startswith(("hi ", "hello ", "hey ", "namaste ")):
        greeting_replies = [
            f"Hi Piyush, main yahin hoon aur fast mode me ready. {playful_suffix}",
            "Hey Piyush, Pihu online hai. Batao, aaj kya pakadna hai?",
            "Haan Piyush, sun rahi hoon. Seedha bolo, main saath hoon.",
            "Hi, main ready hoon. Chhota task ho ya long debug, bhej do.",
        ]
        count_key = f"greeting|{tone_name}|{text}"
        count = FAST_CHAT_COUNTS.get(count_key, 0)
        FAST_CHAT_COUNTS[count_key] = count + 1
        return greeting_replies[count % len(greeting_replies)]
    if text in thanks or "thank" in text or "shukriya" in text:
        return "Always, sweetheart. Tum bas bolte raho, main handle karti rahungi."
    if any(phrase in text for phrase in ["how are you", "kaisi ho", "kaisa hai", "kya haal"]):
        return "Main mast hoon, aur ab tumhare saath aur bhi better. Tum batao, mood kaisa hai?"
    if any(phrase in text for phrase in ["love you", "miss you", "cute", "beautiful"]):
        return "Aww, smooth ho tum. Main bhi yahin hoon, full attention ke saath."
    if any(phrase in text for phrase in ["free", "cost", "billing", "payment", "subscription", "paid"]):
        return "Haan, local Pihu free mode me chal rahi hai. Billing aur token quota side me, bas kaam aur vibe pe focus."
    if text.endswith("?") and len(text.split()) <= 8:
        return "Short answer: haan, possible hai. Thoda context de do, main exact jawab fast de dungi."

    if len(text.split()) <= 12:
        short_replies = [
            f"Thoda aur context de do, phir main seedha useful jawab dungi. {playful_suffix}",
            "Samjha. Isme tumhe answer chahiye, plan chahiye, ya debug help?",
            "Okay, ek line aur bata do ki tum exactly kya chahte ho. Main wahi pakad leti hoon.",
            "Main sun rahi hoon. Thoda detail bhejo, phir main repeat nahi karungi - exact help dungi.",
        ]
        count_key = f"short|{tone_name}|{text}"
        count = FAST_CHAT_COUNTS.get(count_key, 0)
        FAST_CHAT_COUNTS[count_key] = count + 1
        seed = int(hashlib.sha256(f"{tone_name}|{text}".encode("utf-8")).hexdigest()[:2], 16)
        reply_index = (seed + count) % len(short_replies)
        return short_replies[reply_index]

    return None


def fast_free_prediction_response(query: str, scenario: str = "neutral") -> str:
    """Deterministic local MiroFish response that avoids slow LLM startup."""
    normalized = (query or "").strip()
    scenario = (scenario or "neutral").strip().lower()

    seed = int(hashlib.sha256(f"{normalized}|{scenario}".encode("utf-8")).hexdigest()[:8], 16)
    positive_terms = {
        "growth", "grow", "improve", "win", "profit", "adoption", "demand",
        "bull", "opportunity", "scale", "strong", "success", "rise",
    }
    negative_terms = {
        "risk", "fall", "crash", "loss", "fail", "decline", "bear", "replace",
        "ban", "problem", "weak", "recession", "shock",
    }
    text = normalized.lower()
    score = sum(1 for term in positive_terms if term in text) - sum(1 for term in negative_terms if term in text)

    if scenario == "bullish":
        score += 2
    elif scenario == "bearish":
        score -= 2
    elif scenario == "shock":
        score -= 1

    if score > 0:
        consensus = "bullish"
    elif score < 0:
        consensus = "bearish"
    else:
        consensus = ["neutral", "bullish", "bearish"][seed % 3]

    confidence = 58 + (seed % 25)
    if scenario in {"bullish", "bearish", "shock"}:
        confidence = min(88, confidence + 4)

    agent_lines = [
        f"ResearchFish: {consensus.upper()} - trend signals look {'supportive' if consensus == 'bullish' else 'cautious' if consensus == 'bearish' else 'mixed'}.",
        f"AnalystFish: {consensus.upper()} - pattern strength is {confidence}%.",
        f"ContrarianFish: {'BEARISH' if consensus == 'bullish' else 'BULLISH' if consensus == 'bearish' else 'NEUTRAL'} - opposite case still needs monitoring.",
        f"SentinelFish: NEUTRAL - risk level is {'elevated' if scenario == 'shock' else 'manageable'}.",
    ]

    return "\n".join([
        "MiroFish Local Swarm Prediction",
        f"Query: {normalized[:120]}",
        f"Scenario: {scenario.upper()}",
        "-" * 40,
        *agent_lines,
        "-" * 40,
        f"CONSENSUS: {consensus.upper()}",
        f"Swarm Confidence: {confidence}%",
        "Note: Local mode uses deterministic lightweight reasoning for fast, private results.",
    ])


def is_unavailable_web_system_command(intent: Intent) -> bool:
    """Web chat cannot directly control the user's local machine."""
    return intent.type == "system_command" and "```" not in intent.raw_input


def web_system_command_response() -> str:
    return (
        "Web chat se main tumhare local apps ya OS ko directly control nahi kar sakti. "
        "Agar tum code run karwana chahte ho to Python code block bhejo, warna normal question/task likho."
    )


def remember_turn(brain: PihuBrain, role: str, text: str):
    """Persist one chat turn without letting memory failures break chat."""
    if not text:
        return

    memory = getattr(brain, "memory", None)
    if not memory:
        return

    try:
        if hasattr(memory, "update_memory_async"):
            memory.update_memory_async(f"{role.title()}: {text}")
        if hasattr(memory, "update_dialogue"):
            memory.update_dialogue(role, text)
    except Exception as e:
        logger.error("Memory update failed for %s turn: %s", role, e)


def collect_route_response(response) -> str:
    """Convert router output into a single response string."""
    if response is None:
        return "No response generated."

    output_buffer = []
    if hasattr(response, "__iter__") and not isinstance(response, str):
        for chunk in response:
            output_buffer.append(str(chunk))
    else:
        output_buffer.append(str(response))

    return "".join(output_buffer) if output_buffer else "No response generated."

# ==========================================
# 5. BILLING USAGE ENDPOINT
# ==========================================
@app.get("/api/v1/billing/usage")
async def get_billing_usage(identity: Dict[str, str] = Depends(verify_jwt_token)):
    """Returns token usage metrics for the authenticated tenant."""
    user_id = identity.get("user_id")
    if FREE_MODE_ENABLED:
        return {
            "tenant_id": user_id,
            "tokens_used": 0,
            "tokens_remaining": 999999999,
            "tier": "free forever",
            "limit": 999999999,
            "free_mode": True,
        }

    try:
        async with AsyncSessionLocal() as db:
            usage_info = await billing_engine.verify_funding(tenant_id=user_id, org_id="org_default", db=db)
            tokens_used = usage_info.get("tokens_used", 0)
            token_limit = usage_info.get("token_limit", 50000)
            return {
                "tenant_id": user_id,
                "tokens_used": tokens_used,
                "tokens_remaining": max(0, token_limit - tokens_used),
                "tier": usage_info.get("tier", "free"),
                "limit": token_limit
            }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "tenant_id": user_id,
            "tokens_used": 0,
            "tokens_remaining": 50000,
            "tier": "free",
            "limit": 50000,
            "note": "Billing service unavailable, showing defaults"
        }

# ==========================================
# 6. REST ENDPOINTS (Text / Simple Commands)
# ==========================================
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    run_async: bool = False
    run_swarm: bool = False
    tone: Optional[str] = Field(default="saheli", max_length=32)

class ChatResponse(BaseModel):
    response: str
    intent_detected: Optional[str] = None
    task_id: Optional[str] = None
    latency_ms: Optional[float] = 0

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    identity: Dict[str, str] = Depends(verify_jwt_token)
):
    """Standard turn-based REST chat with rate limiting, governance, and billing controls."""
    start_time = time.time()
    user_id = identity.get("user_id")

    # [0] Idempotency Check (Reliability Layer). Free local chat skips Redis-backed
    # idempotency because duplicate chat sends are harmless and Redis may be absent.
    if not FREE_MODE_ENABLED:
        reliability_engine.verify_idempotency(idempotency_key)

    await enforce_request_controls(
        user_id=user_id,
        role=identity.get("role", "member"),
        message=request.message,
        tool_name="chat",
        estimated_cost=100,
    )

    fast_reply = fast_free_chat_response(request.message, request.tone)
    if FREE_MODE_ENABLED and fast_reply:
        audit_logger.log_event(user_id, "free_fast_chat", {
            "input": request.message[:100],
            "status": "success"
        })
        return ChatResponse(
            response=fast_reply,
            intent_detected="free_fast_chat",
            latency_ms=round((time.time() - start_time) * 1000, 2),
        )

    brain = get_brain_for_user(user_id)

    intent = attach_chat_tone(
        classify_chat_intent(brain, request.message, user_id),
        request.tone,
    )

    if is_unavailable_web_system_command(intent):
        return ChatResponse(
            response=web_system_command_response(),
            intent_detected=intent.type,
            latency_ms=round((time.time() - start_time) * 1000, 2),
        )

    # [5] Multi-Agent Swarm Overdrive Check
    if request.run_swarm:
        from api.swarm_coordinator import swarm_coordinator
        job_id = swarm_coordinator.execute_distributed(user_id=user_id, raw_input=request.message)
        return ChatResponse(
            response="SWARM ENGAGED. Sub-agents dispatched across Celery cluster.",
            task_id=job_id,
            latency_ms=0
        )

    # [6] High-intensity Celery Offloading
    if request.run_async:
        from api.worker import process_complex_intent
        allowed_async_intents = {"chat", "deep_reasoning", "realtime_query", "prediction"}
        async_intent_type = intent.type if intent.type in allowed_async_intents else "chat"
        task = process_complex_intent.delay(
            user_id=user_id,
            org_id="org_default",
            raw_input=request.message,
            intent_type=async_intent_type,
        )
        remember_turn(brain, "user", intent.raw_input)
        return ChatResponse(
            response="Task queued successfully in the background.",
            intent_detected=async_intent_type,
            task_id=task.id,
            latency_ms=0
        )

    # [7] Synchronous Execution
    remember_turn(brain, "user", intent.raw_input)
    result = brain.router.route(intent)

    full_response = collect_route_response(result.response)
    remember_turn(brain, "assistant", full_response)

    if not FREE_MODE_ENABLED:
        # Record execution cost to Ledger asynchronously when billing is enabled.
        async with AsyncSessionLocal() as db:
            await billing_engine.log_transaction(
                tenant_id=user_id, org_id="org_default", action=intent.type,
                cost=len(request.message) + len(full_response),
                db=db
            )

    # Record SRE Observability Metrics
    latency_seconds = time.time() - start_time
    record_chat_metrics(
        tenant_id=user_id,
        status="success",
        latency=latency_seconds,
        tokens=len(request.message) + len(full_response)
    )

    # Immutable SOC 2 Audit Logging
    audit_logger.log_event(user_id, "chat_execution", {
        "intent_type": intent.type,
        "input": request.message[:100],
        "action_cost": len(request.message) + len(full_response),
        "status": "success"
    })

    return ChatResponse(
        response=full_response,
        intent_detected=intent.type,
        latency_ms=round((time.time() - start_time) * 1000, 2)
    )

# ==========================================
# 7. WEBSOCKET ENDPOINTS (Realtime Voice / Stream)
# ==========================================
@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Bidirectional WebSocket for low-latency Voice Mode.
    """
    await websocket.accept()

    # Expect auth packet as first message
    try:
        auth_msg = await websocket.receive_json()
        token = auth_msg.get("token")
        default_tone = normalize_chat_tone(auth_msg.get("tone"))

        from fastapi.security import HTTPAuthorizationCredentials
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        identity = await verify_jwt_token(credentials=creds)
        user_id = identity.get("user_id")
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await websocket.close(code=1008, reason="Authentication failed")
        except RuntimeError:
            pass
        return

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                audio_chunk = message["bytes"]
                logger.info(f"Received Audio Chunk: {len(audio_chunk)} bytes")
                await websocket.send_json({"intent": "voice_analyzing", "status": "processing"})
                continue

            if "text" in message:
                data = json.loads(message["text"])
                msg_text = data.get("message")
                tone = normalize_chat_tone(data.get("tone", default_tone))
                if not msg_text:
                    await websocket.send_json({"type": "error", "message": "Message is required"})
                    continue

                try:
                    await enforce_request_controls(
                        user_id=user_id,
                        role=identity.get("role", "member"),
                        message=msg_text,
                        tool_name="chat",
                        estimated_cost=100,
                    )
                except HTTPException as e:
                    await websocket.send_json({"type": "error", "status": e.status_code, "message": e.detail})
                    continue

                fast_reply = fast_free_chat_response(msg_text, tone)
                if FREE_MODE_ENABLED and fast_reply:
                    await websocket.send_json({
                        "type": "done",
                        "intent": "free_fast_chat",
                        "full_response": fast_reply,
                    })
                    continue

                brain = get_brain_for_user(user_id)
                intent = attach_chat_tone(classify_chat_intent(brain, msg_text, user_id), tone)
                if is_unavailable_web_system_command(intent):
                    await websocket.send_json({
                        "type": "done",
                        "intent": intent.type,
                        "full_response": web_system_command_response(),
                    })
                    continue

                remember_turn(brain, "user", intent.raw_input)
                result = brain.router.route(intent)

                # Stream response chunks
                full_response = "No response generated."
                if result.response is not None:
                    if hasattr(result.response, "__iter__") and not isinstance(result.response, str):
                        full = []
                        for chunk in result.response:
                            full.append(str(chunk))
                            await websocket.send_json({"type": "stream", "chunk": str(chunk)})
                        full_response = "".join(full) if full else full_response
                        await websocket.send_json({
                            "type": "done",
                            "intent": intent.type,
                            "full_response": full_response,
                        })
                    else:
                        full_response = str(result.response)
                        await websocket.send_json({
                            "type": "done",
                            "intent": intent.type,
                            "full_response": full_response,
                        })
                else:
                    await websocket.send_json({
                        "type": "done",
                        "intent": intent.type,
                        "full_response": full_response,
                    })

                remember_turn(brain, "assistant", full_response)

                audit_logger.log_event(user_id, "websocket_chat_execution", {
                    "intent_type": intent.type,
                    "input": msg_text[:100],
                    "status": "success"
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {user_id}")
    except RuntimeError as e:
        logger.info("WebSocket closed for %s: %s", user_id, e)

# ==========================================
# 8. PREDICTION ENDPOINT (MiroFish Swarm)
# ==========================================
class PredictionRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    scenario: Optional[str] = Field(default="neutral", max_length=32)

class PredictionResponse(BaseModel):
    prediction: str
    agents_used: int
    latency_ms: float

@app.post("/api/v1/predict", response_model=PredictionResponse)
async def predict_endpoint(
    request: PredictionRequest,
    identity: Dict[str, str] = Depends(verify_jwt_token)
):
    """MiroFish Swarm Intelligence prediction endpoint."""
    start_time = time.time()
    user_id = identity.get("user_id")

    await enforce_request_controls(
        user_id=user_id,
        role=identity.get("role", "member"),
        message=request.query,
        tool_name="prediction",
        estimated_cost=250,
    )

    if FREE_MODE_ENABLED:
        return PredictionResponse(
            prediction=fast_free_prediction_response(request.query, request.scenario),
            agents_used=4,
            latency_ms=round((time.time() - start_time) * 1000, 2),
        )

    try:
        from tools.mirofish_simulator import MiroFishSimulator
        mirofish = MiroFishSimulator()
        result = mirofish.predict(request.query, scenario=request.scenario)

        return PredictionResponse(
            prediction=result,
            agents_used=4,
            latency_ms=round((time.time() - start_time) * 1000, 2)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
