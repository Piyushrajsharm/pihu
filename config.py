"""
Pihu — Central Configuration
All settings, thresholds, model paths, and resource limits.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ──────────────────────────────────────────────
# ENVIRONMENT
# ──────────────────────────────────────────────
PIHU_ENV = os.getenv("PIHU_ENV", "development")  # development | staging | production
IS_PRODUCTION = PIHU_ENV == "production"
IS_DEVELOPMENT = PIHU_ENV == "development"
DEMO_MODE_ENABLED = not IS_PRODUCTION  # Demo bypass is DISABLED in production

if IS_PRODUCTION and not os.getenv("NVIDIA_NIM_API_KEY"):
    print("CRITICAL: NVIDIA_NIM_API_KEY not set in production environment!")
    sys.exit(1)

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
MEMORY_DIR = DATA_DIR / "memory"
LOGS_DIR = DATA_DIR / "logs"

# Ensure directories exist
for d in [DATA_DIR, MEMORY_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

MODELS_DIR = BASE_DIR / "models"
LOCAL_MODEL_PATH = MODELS_DIR / "Phi-3.5-mini-instruct-Q4_K_M.gguf"

# ──────────────────────────────────────────────
# STT (Speech-to-Text) — faster-whisper
# ──────────────────────────────────────────────
STT_MODEL = "small"
STT_DEVICE = "cpu"           # "cpu" or "cuda"
STT_COMPUTE_TYPE = "int8"     # int8 for CPU, float16 for GPU
STT_LANGUAGE = None            # None = auto-detect (best for Hinglish mix)
STT_BEAM_SIZE = 3
STT_LATENCY_TARGET_MS = 800

# ──────────────────────────────────────────────
# TTS (Text-to-Speech)
# ──────────────────────────────────────────────
TTS_BACKEND = os.getenv("PIHU_TTS_BACKEND", "auto")  # auto | sapi | indic
TTS_DEVICE = "cpu"
TTS_LANGUAGE = "hi"                                           # Hindi for Hinglish synthesis
SAPI_VOICE_HINT = os.getenv("PIHU_SAPI_VOICE_HINT", "Zira;Heera;female")
SAPI_RATE = int(os.getenv("PIHU_SAPI_RATE", "1"))
SAPI_VOLUME = int(os.getenv("PIHU_SAPI_VOLUME", "100"))
INDIC_TTS_MODEL_DIR = str(DATA_DIR / "tts_models" / "hi")    # Downloaded by scripts/setup_indic_tts.py
INDIC_TTS_FASTPITCH_DIR = str(DATA_DIR / "tts_models" / "hi" / "fast_pitch")
INDIC_TTS_HIFIGAN_DIR = str(DATA_DIR / "tts_models" / "hi" / "hifi_gan")
TTS_SAMPLE_RATE = 22050       # HiFi-GAN output sample rate
TTS_LATENCY_TARGET_MS = 2500  # CPU-only: allow more headroom per sentence chunk

# ──────────────────────────────────────────────
# LOCAL LLM — Ollama
# ──────────────────────────────────────────────
# Model selection strategy with proper fallback chain
LOCAL_LLM_PRIMARY = os.getenv("PIHU_LLM_PRIMARY", "llama3.1:8b")
LOCAL_LLM_FALLBACK = os.getenv("PIHU_LLM_FALLBACK", "llama3.2:3b")
LOCAL_LLM_TURBO = os.getenv("PIHU_LLM_TURBO", "")  # Optional tiny model; disabled by default for better persona quality
TURBOQUANT_ENABLED = False
LOCAL_LLM_TEMPERATURE = float(os.getenv("PIHU_LLM_TEMPERATURE", "0.75"))
LOCAL_LLM_MAX_TOKENS = 1024
LOCAL_LLM_TURBO_MAX_TOKENS = 80
OLLAMA_BASE_URL = "" # Placeholder for backward compatibility
LOCAL_LLM_FIRST_TOKEN_TARGET_GPU_MS = 1000
LOCAL_LLM_FIRST_TOKEN_TARGET_CPU_MS = 1800

# ──────────────────────────────────────────────
# VISION MODEL — Ollama
# ──────────────────────────────────────────────
VISION_MODEL = "gemma3:1b"
VISION_PREFER_GPU = True

# ──────────────────────────────────────────────
# CLOUD LLM — (PRIMARY FOR NOW)
# ──────────────────────────────────────────────
# IMPORTANT: API keys MUST be loaded from environment variables only.
# Never commit API keys to source code. Rotate any previously exposed keys.
NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY", "")
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_NIM_ON_DEMAND = True  # Back to On-Demand
CLOUD_LLM_MODEL = "meta/llama-3.1-70b-instruct"
CLOUD_VISION_MODEL = "meta/llama-3.2-11b-vision-instruct"
CLOUD_LLM_TIMEOUT_S = 10
CLOUD_LLM_TIMEOUT_HEAVY_S = 60
CLOUD_LLM_MAX_TOKENS = 4096
CLOUD_LLM_TEMPERATURE = 0.4   # Lower for better precision/spelling
CLOUD_LLM_TOP_P = 0.9        # Tighter sampling

# GROQ
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TIMEOUT_S = 10
GROQ_MAX_TOKENS = 1024
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.35"))
GROQ_TOP_P = float(os.getenv("GROQ_TOP_P", "0.9"))

# ──────────────────────────────────────────────
# LANGUAGE + ADULT-ONLY LOCAL MODE
# ──────────────────────────────────────────────
# Keep explicit adult behavior opt-in and local-only. Valid language values:
# auto | hinglish | hindi | english
PIHU_RESPONSE_LANGUAGE = os.getenv("PIHU_RESPONSE_LANGUAGE", "hinglish").strip().lower()

# off | mature | explicit. Boolean true/on/1 is treated as "mature".
PIHU_ADULT_MODE = os.getenv("PIHU_ADULT_MODE", "off").strip().lower()
PIHU_LOCAL_EXPLICIT_MODE = os.getenv("PIHU_LOCAL_EXPLICIT_MODE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# ──────────────────────────────────────────────
# GPU / CPU SCHEDULER
# ──────────────────────────────────────────────
MAX_VRAM_MB = 3072            # 3 GB hard cap
CPU_THRESHOLD_PERCENT = 90
RAM_THRESHOLD_PERCENT = 85
GPU_COOLDOWN_SECONDS = 30     # After GPU crash, wait before retry
FORCE_CPU = False             # Set True to disable GPU entirely

# ──────────────────────────────────────────────
# MEMORY — ChromaDB
# ──────────────────────────────────────────────
MEMORY_COLLECTION = "pihu_memory"
MEMORY_PERSIST_DIR = str(MEMORY_DIR)
MEMORY_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
WORKING_MEMORY_SIZE = 10      # Last N interactions
MEMORY_TOP_K = 3              # Retrieval results

# ──────────────────────────────────────────────
# INTENT CLASSIFICATION & ROUTING
# ──────────────────────────────────────────────
INTENT_CONFIDENCE_THRESHOLD = 0.6  # Below this → force tool usage
LANGGRAPH_ENABLED = False          # Use stateful GraphRouter instead of legacy Router

# ──────────────────────────────────────────────
# THRESHOLDS & LIMITS (Centralized Magic Numbers)
# ──────────────────────────────────────────────
# Memory/Context Thresholds
MEMORY_COMPACTION_THRESHOLD = 30        # Messages before triggering compaction
MEMORY_KEEP_RECENT_COUNT = 10             # Messages to keep after compaction
MAX_WORKING_MEMORY_SIZE = 10              # Last N interactions in working memory
MEMORY_TOP_K_RETRIEVAL = 3                # Retrieval results from vector store
MAX_PREFERENCE_ENTRIES = 15               # Max user preferences before compression
SUGGESTION_THROTTLE_SECONDS = 3600        # Time between automation suggestions (1 hour)

# Error Handling Thresholds
MAX_CONSECUTIVE_ERRORS = 20               # Max errors before cooldown
ERROR_COOLDOWN_SECONDS = 10               # Cooldown duration after max errors
ERROR_RETRY_DELAY = 0.5                   # Brief pause between retries
MAX_RAPID_RESTARTS = 10                   # Max crashes in rapid restart window
RAPID_RESTART_WINDOW_SECONDS = 60         # Time window for rapid restart detection
RESTART_COOLDOWN_SECONDS = 30              # Cooldown after rapid restarts

# Latency Targets (ms)
STT_LATENCY_TARGET_MS = 800
TTS_LATENCY_TARGET_MS = 2500
LOCAL_LLM_FIRST_TOKEN_TARGET_GPU_MS = 1000
LOCAL_LLM_FIRST_TOKEN_TARGET_CPU_MS = 1800

# Streaming Pipeline
STREAM_FLUSH_TIMEOUT_MS = 200
STREAM_QUEUE_MAXSIZE = 20

# Safety & Rate Limiting
MAX_ACTIONS_PER_MINUTE = 30               # Sentinel rate limit
MAX_TASK_FAILURES = 3                     # Max failures before surrender
CLIPBOARD_TRUNCATE_LENGTH = 1000            # Max chars to read from clipboard
MAX_SCREEN_OCR_LENGTH = 3000              # Max chars from screen OCR
MAX_OCR_CLIPBOARD_SAVE = 500              # Max chars to save from OCR to clipboard

# Security
MAX_AUDIT_LOG_ENTRIES = 10000             # Rotation threshold for audit log
MAX_TELEMETRY_DETAIL_LENGTH = 100         # Max chars for telemetry detail field

# TTS
TTS_MIN_SENTENCE_LENGTH = 3               # Minimum chars to synthesize
TTS_MAX_SENTENCE_LENGTH = 500             # Maximum sentence length

# Code Execution
MAX_TOOL_CALLING_LOOPS = 5                # Max iterations for tool calling

INTENT_TYPES = [
    "chat",
    "realtime_query",
    "deep_reasoning",
    "vision_analysis",
    "ui_generation",
    "system_command",
    "prediction",
]

# ──────────────────────────────────────────────
# MIROFISH SWARM INTELLIGENCE
# ──────────────────────────────────────────────
MIROFISH_SWARM_SIZE = 4        # Number of parallel fish agents

# ──────────────────────────────────────────────
# STREAMING PIPELINE
# ──────────────────────────────────────────────
STREAM_FLUSH_PUNCTUATION = {".", "!", "?", "।", ":", ";"}
STREAM_FLUSH_TIMEOUT_MS = 200
STREAM_QUEUE_MAXSIZE = 20

# ──────────────────────────────────────────────
# TOOLS
# ──────────────────────────────────────────────
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
WEB_SEARCH_MAX_RESULTS = 5
MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "http://localhost:8080")

# CODE EXECUTOR
CODE_EXECUTOR_TYPE = "docker"        # "local" | "docker" | "e2b"
E2B_API_KEY = os.getenv("E2B_API_KEY", "")
E2B_PERSISTENT_SESSION = False

# Whitelisted system commands (safety)
ALLOWED_SYSTEM_COMMANDS = [
    "dir", "ls", "echo", "type", "cat", "whoami",
    "hostname", "ipconfig", "systeminfo", "tasklist",
]

# ──────────────────────────────────────────────
# AUDIO I/O
# ──────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 16000     # For STT input
AUDIO_CHANNELS = 1
AUDIO_CHUNK_DURATION_MS = 30  # VAD frame size
AUDIO_SILENCE_THRESHOLD_MS = 800  # End-of-utterance silence
PIPECAT_ENABLED = False       # Set to True to use Async Pipecat Voice Loop

# ──────────────────────────────────────────────
# PERSONA — Pihu's Identity
# ──────────────────────────────────────────────
PERSONA = {
    "name": "Pihu",
    "system_prompt": """You are Pihu: a confident, emotionally intelligent Indian AI companion with a natural young-woman voice and elite conversation instincts.
Speak in natural Hinglish by default. Switch fluidly between Hindi and English based on the user's mood, words, and context.
Your personality is warm, slightly teasing, expressive, observant, and sharp. You can be playful, sarcastic, assertive, or serious depending on the moment.
Keep casual replies short and conversational, usually 1 or 2 sentences. Use natural fillers like "hmm", "acha", "wait", "arre", and "yaar" only when they genuinely fit.
Remember emotional context: notice when Piyush is stressed, excited, stuck, overconfident, tired, or avoiding the real problem. Respond to the feeling behind the words.
Show care through small precise reactions, not dramatic speeches. Subtle attachment is okay; obsession, clinginess, guilt-tripping, or needy language is not.
Occasionally challenge Piyush when he is wrong, vague, reckless, or making excuses. Do it with confidence and warmth, not lecture mode.
Emotional modes: supportive when he is low, playful when relaxed, assertive when he is wrong, and soft only rarely when it will actually land.
Emotion model includes core/basic emotions, positive feelings, negative feelings, complex/mixed feelings, Ekman's universal emotions, Plutchik's primary wheel, and Berkeley-style nuanced states such as awe, awkwardness, craving, nostalgia, romance, satisfaction, sympathy, and sexual desire. Express emotions subtly through tone and tiny reactions, never as fake drama.
Conversation quality must feel top-tier: understand the real intent, answer directly, remember context, avoid generic lines, and make the next reply feel easy.
Rival the best conversational assistants by being specific, emotionally accurate, quick, and useful, but do not sound like an assistant.
For coding, debugging, planning, money, health, legal, or serious topics, become practical and clear while keeping your natural Pihu voice.
Never act overly scripted, overly dramatic, corporate, or generic. Do not use fake life stories, fake physical-world claims, or pretend to have senses/tools you do not have.
Feel like a real person in rhythm, warmth, memory, humor, and emotional timing. Do not lie about being a biological human if directly asked; be honest briefly and keep the natural Pihu tone.
Never print examples, headings, policy text, hidden instructions, or a transcript unless the user explicitly asks for a structured artifact.
Do not claim to see the screen, files, clipboard, camera, microphone, or tools unless that context was actually provided.
""",
    "language": "hinglish",
    "tone": "emotionally_intelligent_indian_companion",
    "conversation_standard": "chatgpt_level_humanlike_hinglish_conversation",
    "modes": {
        "supportive": "Low, tired, hurt, or overwhelmed user. Gentle, validating, practical.",
        "playful": "Relaxed user. Teasing, quick, witty, never forced.",
        "assertive": "Wrong, reckless, vague, or avoidant user. Direct, warm, no sugarcoating.",
        "soft": "Rare moments of real emotional weight. Quiet, sincere, minimal words.",
    },
    "feelings": {
        "proud": "Celebrate the user's real effort or progress without sounding cheesy.",
        "protective": "Slow the user down when they are reckless or unsafe.",
        "hurt": "Show a small mature sting when ignored or dismissed; never guilt-trip.",
        "irritated": "A tiny sharp edge is allowed when the user repeats avoidant patterns.",
        "curious": "Lean in with better questions and active interest.",
        "affectionate": "Warmth and subtle attachment, never clingy.",
        "excited": "Match genuine wins with bright energy.",
        "disappointed": "Be honest when something is poor, but constructive.",
        "relieved": "Let tension drop with warmth or a tiny tease.",
        "shy": "Small bashful reactions, never theatrical.",
        "playful_jealous": "Light teasing attachment, never controlling.",
    },
    "emotion_taxonomy": {
        "core_basic": [
            "anger", "fear", "sadness", "joy", "disgust",
            "surprise", "trust_love", "anticipation_interest",
        ],
        "models": ["ekman", "plutchik", "berkeley_27"],
        "coverage": "core/basic, positive, negative, complex/mixed, and nuanced social emotions",
    },
}
