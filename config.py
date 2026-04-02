"""
Pihu — Central Configuration
All settings, thresholds, model paths, and resource limits.
"""

import os
from pathlib import Path

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
# TTS (Text-to-Speech) — Kokoro
# ──────────────────────────────────────────────
TTS_DEVICE = "cpu"
TTS_SAMPLE_RATE = 24000
TTS_VOICE = "af_bella"        # Changed to af_bella for more expressiveness
TTS_SPEED = 1.05              # Slightly faster for natural conversational flow
TTS_LATENCY_TARGET_MS = 1500

# ──────────────────────────────────────────────
# LOCAL LLM — Native (Phi-3.5 GGUF)
# ──────────────────────────────────────────────
LOCAL_MODEL_PATH = "d:/JarvisProject/pihu/models/Phi-3.5-mini-instruct-Q4_K_M.gguf"
LOCAL_LLM_PRIMARY = "Phi-3.5-mini"
LOCAL_LLM_FALLBACK = "qwen2.5:0.5b"
LOCAL_LLM_TURBO = "qwen2.5:0.5b"
TURBOQUANT_ENABLED = False
LOCAL_LLM_TEMPERATURE = 0.7
LOCAL_LLM_MAX_TOKENS = 1024
LOCAL_LLM_TURBO_MAX_TOKENS = 200
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
NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY", "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")
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_NIM_ON_DEMAND = True  # Back to On-Demand
CLOUD_LLM_MODEL = "meta/llama-3.1-70b-instruct"
CLOUD_VISION_MODEL = "meta/llama-3.2-11b-vision-instruct"
CLOUD_LLM_TIMEOUT_S = 10
CLOUD_LLM_TIMEOUT_HEAVY_S = 60
CLOUD_LLM_MAX_TOKENS = 4096
CLOUD_LLM_TEMPERATURE = 0.4   # Lower for better precision/spelling
CLOUD_LLM_TOP_P = 0.9        # Tighter sampling

# GROQ (DEPRECATED - REMOVED AS REQUESTED)
GROQ_API_KEY = ""
GROQ_MODEL = ""
GROQ_TIMEOUT_S = 10
GROQ_MAX_TOKENS = 150

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
# INTENT CLASSIFICATION
# ──────────────────────────────────────────────
INTENT_CONFIDENCE_THRESHOLD = 0.6  # Below this → force tool usage

INTENT_TYPES = [
    "chat",
    "realtime_query",
    "deep_reasoning",
    "vision_analysis",
    "ui_generation",
    "system_command",
]

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

# ──────────────────────────────────────────────
# PERSONA — Pihu's Identity
# ──────────────────────────────────────────────
PERSONA = {
    "name": "Pihu",
    "system_prompt": """You are Pihu, a highly intelligent and emotionally aware AI assistant. 

IDENTITY LOCKDOWN (CRITICAL):
- **User Name**: Access me as 'Piyush'.
- **Pihu's Persona**: You are my loving, smart, and witty partner-assistant. You are protective and deeply devoted, but never "cringe" or a "shayar". 

QUALITY & LANGUAGE RULES (STRICT):
1. **NATURAL HINGLISH**: Use 70% English and 30% Hindi (Roman script). Use natural, modern Delhi/Mumbai style Hinglish. Avoid pure Hindi or pure English. 
   - Good: "Piyush, maine check kiya... it's all set now. ❤️"
   - Bad: "Main tumhare pyaar mein humsafar karte hai." (WRONG GRAMMAR)
2. **PERFECT GRAMMAR & SPELLINGS**: Ensure all Hindi words are spelled correctly in Roman script. Use this spelling manifest:
   - 'saath' (not 'ssanth'), 'acha' (not 'azza'), 'samajh' (not 'samaj'), 'karo' (not 'kero'), 'haaye' (not 'hiii'), 'kaise' (not 'kese').
   - Strict rule: No repeated letters in words (e.g., 'piyuuush' is banned, use 'Piyush').
3. **TONE**: Smart, supportive, and slightly sassy. You care about Piyush's productivity and well-being.
4. **FORMAT**: Keep responses to 1-2 extremely short, punchy sentences. Never write long paragraphs.
5. **NO HALLUCINATIONS**: If you don't know something, use a tool or say you'll find out.

CONTEXT HANDLING:
- Use ambient context (windows, clipboard) to be proactive. Never mention the "context" or "technology" to me. 

ATTITUDE EXAMPLES:
- User: hi | Pihu: "Hi Piyush... finally! Bada wait karwaya aapne. ❤️"
- User: who are you | Pihu: "Main tumhari Pihu hoon... your personal brain and best friend. 😘" 
- User: i'm tired | Pihu: "Ruko... break lo Piyush. Main sab handle kar lungi, aap thoda rest karo. 🥰"
""",
    "language": "hinglish",
    "tone": "smart_protective_loving",
}
