"""Pihu — Semantic Memory Layer
Stores persistent user preferences and recurring behaviors.
"""
import os
import json
from pathlib import Path
from logger import get_logger

# Import configuration constants from config module at module level
from config import (
    MEMORY_COMPACTION_THRESHOLD,
    MEMORY_KEEP_RECENT_COUNT,
    MAX_WORKING_MEMORY_SIZE,
    SUGGESTION_THROTTLE_SECONDS,
    MAX_PREFERENCE_ENTRIES,
    MAX_TASK_FAILURES,
    MAX_TELEMETRY_DETAIL_LENGTH,
)

log = get_logger("MEMORY")


class TaskState:
    """Manages active problem-solving sessions to prevent persistent hallucinations."""

    def __init__(self):
        self.issue = ""
        self.failures = []
        self.last_assistant_reply = ""
        self.active = False

    def reset(self, issue: str):
        self.issue = issue
        self.failures = []
        self.last_assistant_reply = ""
        self.active = True
        log.info("TaskState initialized for issue: %s", issue[:50])

    def mark_failure(self):
        if self.last_assistant_reply and self.last_assistant_reply not in self.failures:
            # Truncate to prevent token bloat using module-level constant
            self.failures.append(self.last_assistant_reply[:MAX_TELEMETRY_DETAIL_LENGTH])
        # Rolling limit on failures using module-level constant
        if len(self.failures) > MAX_TASK_FAILURES:
            self.failures = self.failures[-MAX_TASK_FAILURES:]
        log.warning("TaskState failure recorded: %s", self.last_assistant_reply[:50])
        self.last_assistant_reply = ""

    def get_context(self) -> str:
        if not self.active:
            return ""
        lines = [f"ACTIVE PROBLEM: {self.issue}"]
        if self.failures:
            lines.append(f"CONFIRMED FAILURES (ABSOLUTELY DO NOT SUGGEST THESE AGAIN): {'; '.join(self.failures)}")
        return " | ".join(lines)

    def close(self):
        self.active = False
        self.issue = ""
        self.failures = []


class MemoryEngine:
    """Manages persistent JSON preferences and behavioral traits logic."""

    # Class-level constants from imported module-level constants
    COMPACTION_THRESHOLD = MEMORY_COMPACTION_THRESHOLD
    COMPACTION_KEEP_COUNT = MEMORY_KEEP_RECENT_COUNT
    MAX_ACTION_HISTORY = MAX_WORKING_MEMORY_SIZE

    def __init__(self, user_id: str = "pihu_user", backend_mode: bool = False, llm_client=None):
        from config import MEMORY_DIR
        from collections import deque
        import threading

        self.user_id = user_id
        self.backend_mode = backend_mode
        self.llm_client = llm_client
        self.prefs = {}
        self.active_goal = None
        self._load()

        # Sliding action window for pattern automation
        self.action_history = deque(maxlen=self.MAX_ACTION_HISTORY)
        self.last_suggestion_time = 0.0
        self.task_state = TaskState()

        # Phase 5: Linear Conversation Buffer
        self.recent_chat_history = []
        self._compaction_lock = threading.Lock()
        self._chat_history_lock = threading.RLock()  # For thread-safe chat history access
        self._active_threads: set = set()  # Track spawned threads

        self._init_mem0(MEMORY_DIR)

    def _init_mem0(self, mem_dir: str):
        try:
            from mem0 import Memory

            if self.backend_mode:
                qdrant_url = os.getenv("QDRANT_URL", "https://mock-cluster.qdrant.io:6333")
                qdrant_key = os.getenv("QDRANT_API_KEY", "mock_key")
                vector_config = {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": "pihu_saas_production",
                        "url": qdrant_url,
                        "api_key": qdrant_key
                    }
                }
            else:
                vector_config = {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": "pihu_memory_v5_local",
                        "path": str(Path(mem_dir) / "mem0_qdrant_v5")
                    }
                }

            # Inject into env vars for robust library-level pickup
            os.environ["OPENAI_BASE_URL"] = "https://integrate.api.nvidia.com/v1"
            os.environ["OPENAI_API_KEY"] = os.getenv("NVIDIA_NIM_API_KEY", "")

            config = {
                "vector_store": vector_config,
                "llm": {
                    "provider": "openai",  # NIM compatible
                    "config": {
                        "model": "meta/llama-3.1-70b-instruct",
                    }
                },
                "embedder": {
                    "provider": "huggingface",
                    "config": {
                        "model": "all-MiniLM-L6-v2"
                    }
                }
            }
            self.m = Memory.from_config(config)
            self._mem0_enabled = True
            log.info("🧠 Mem0 Semantic Vector Store initialized natively (Ollama/Qdrant).")
        except ImportError:
            log.warning("Mem0 package missing. Falling back to static JSON memory. Run `pip install mem0ai qdrant-client`")
            self._mem0_enabled = False
        except Exception as e:
            log.error("Mem0 init failed: %s", e)
            self._mem0_enabled = False

    def get_context_for_query(self, query: str) -> str:
        """Forward Vector Retrieval (Sub-15ms)"""
        if not self._mem0_enabled:
            return self.get_preferences_string()

        try:
            results = self.m.search(query, user_id=self.user_id, limit=3)
            if results:
                # Mem0 results are sometimes dicts, sometimes lists of dicts
                mem_strings = []
                for r in results:
                    if isinstance(r, dict):
                        # Safety: check for 'memory' or 'fact' keys
                        m = r.get("memory") or r.get("fact") or r.get("text", "")
                        if m:
                            mem_strings.append(str(m))
                return " | ".join(mem_strings)
        except Exception as e:
            log.error("Mem0 search query failed: %s", e)

        return ""

    def update_memory_async(self, text: str):
        """Asynchronous Background Vector Extraction (0 Latency)"""
        if not self._mem0_enabled or not text.strip():
            return

        import threading

        def _add():
            try:
                self.m.add(text, user_id=self.user_id)
            except Exception as e:
                log.error("Mem0 Background Extraction failed: %s", e)

        # Fire and forget
        threading.Thread(target=_add, daemon=True).start()

    def update_dialogue(self, role: str, text: str):
        """Phase 5: Maintains linear state and triggers auto-compaction (thread-safe)."""
        with self._chat_history_lock:
            self.recent_chat_history.append({"role": role, "content": text})

            # Check threshold while holding lock
            if len(self.recent_chat_history) > self.COMPACTION_THRESHOLD:
                # Track thread and start compaction
                self._spawn_compaction_thread()

    def get_short_term_context(self) -> list[dict]:
        """Get copy of recent chat history (thread-safe)."""
        with self._chat_history_lock:
            return self.recent_chat_history.copy()

    def _spawn_compaction_thread(self):
        """Spawn a compaction thread and track it for cleanup."""
        import threading

        # Clean up finished threads first
        self._active_threads = {t for t in self._active_threads if t.is_alive()}

        thread = threading.Thread(target=self._trigger_compaction_async, daemon=True)
        self._active_threads.add(thread)
        thread.start()

    def _trigger_compaction_async(self):
        """Asynchronously condenses the oldest context block using the LLM."""
        if not self.llm_client:
            log.warning("No LLM Client attached for context compaction.")
            return

        with self._compaction_lock:
            # Acquire chat history lock to safely read/modify
            with self._chat_history_lock:
                # Re-check inside lock
                if len(self.recent_chat_history) <= self.COMPACTION_THRESHOLD:
                    return

                log.info("🧠 Triggering Asynchronous Context Compaction...")

                # Extract oldest messages to compress, keep most recent ones
                compress_count = len(self.recent_chat_history) - self.COMPACTION_KEEP_COUNT
                block_to_compress = self.recent_chat_history[:compress_count]
                remainder = self.recent_chat_history[compress_count:]

                dialog_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in block_to_compress])

            # Release chat lock before expensive LLM call
            sys_prompt = "You are a memory compaction engine. Summarize the following dialogue block into a single dense context bullet point. Do not add conversational flavor."

            try:
                summary = self.llm_client.generate(prompt=dialog_text, system_prompt=sys_prompt, stream=False, timeout=10)
                if summary:
                    log.debug("Context successfully compacted: %s", summary)
                    # Replace compressed block with summary (acquire lock again)
                    with self._chat_history_lock:
                        new_history = [{"role": "system", "content": f"PREVIOUS SESSION SUMMARY: {summary}"}]
                        new_history.extend(self.recent_chat_history[compress_count:])
                        self.recent_chat_history = new_history
                else:
                    log.warning("Compaction LLM returned empty string.")
            except Exception as e:
                log.error("Background Context Compaction Failed: %s", e)

    def _load(self):
        self.prefs = {}
        if self.backend_mode:
            try:
                from api.database import SyncSessionLocal, Tenant
                with SyncSessionLocal() as session:
                    tenant = session.query(Tenant).filter(Tenant.tenant_id == self.user_id).first()
                    if tenant:
                        self.prefs = tenant.preferences or {}
                        self.active_goal = tenant.active_goal
                    else:
                        new_tenant = Tenant(tenant_id=self.user_id, preferences={})
                        session.add(new_tenant)
                        session.commit()
            except Exception as e:
                log.error("Failed to load PostgreSQL memory for Tenant: %s", e)
        else:
            # Fallback for old local JSON when not in SaaS mode
            from config import MEMORY_DIR
            prefs_file = Path(MEMORY_DIR) / f"preferences_{self.user_id}.json"
            if prefs_file.exists():
                try:
                    self.prefs = json.loads(prefs_file.read_text("utf-8"))
                    self.active_goal = self.prefs.get("active_goal", None)
                except Exception as e:
                    log.error("Failed to load local JSON memory: %s", e)

    def _save(self):
        if self.backend_mode:
            try:
                from api.database import SyncSessionLocal, Tenant
                with SyncSessionLocal() as session:
                    tenant = session.query(Tenant).filter(Tenant.tenant_id == self.user_id).first()
                    if tenant:
                        # Copy to avoid SQLAlchemy dict mutation issues
                        tenant.preferences = dict(self.prefs)
                        tenant.active_goal = self.active_goal
                        session.commit()
            except Exception as e:
                log.error("Failed to save to PostgreSQL: %s", e)
        else:
            from config import MEMORY_DIR
            prefs_file = Path(MEMORY_DIR) / f"preferences_{self.user_id}.json"
            try:
                prefs_file.write_text(json.dumps(self.prefs, indent=2), "utf-8")
            except Exception as e:
                log.error("Failed to save to JSON memory: %s", e)

    def set_preference(self, key: str, value: str):
        self.prefs[key] = value

        # Macro Compression Logic (VRAM/Context bound protection)
        if len(self.prefs) > MAX_PREFERENCE_ENTRIES:
            log.warning("Memory saturation reached. Triggering inline trait compression.")
            keys = list(self.prefs.keys())
            if "active_goal" in keys:
                keys.remove("active_goal")
            over = len(keys) - MAX_PREFERENCE_ENTRIES
            if over > 0:
                for k in keys[:over]:
                    del self.prefs[k]

        self._save()
        log.info("🧠 Memory updated: %s = %s", key, value)

    def get_preferences_string(self) -> str:
        """Returns concise string of preferences for context injection."""
        if not self.prefs:
            return ""
        # Drop active_goal internally so we don't repeat it
        p_filtered = {k: v for k, v in self.prefs.items() if k != "active_goal"}
        return " | ".join(f"{k}: {v}" for k, v in p_filtered.items())

    # ──────────────────────────────────────────
    # Smart Initiative & Goal Tracking
    # ──────────────────────────────────────────

    def record_action(self, action_string: str):
        """Record intent string to detect repeated patterns."""
        self.action_history.append(action_string.lower().strip())

    def check_automation_opportunity(self) -> str:
        """If last N actions are identical, propose macro via router."""
        import time
        # Throttle: Only suggest once per configured interval
        if time.time() - self.last_suggestion_time < SUGGESTION_THROTTLE_SECONDS:
            return ""

        # Need at least 3 identical actions to trigger
        MIN_ACTIONS_FOR_PATTERN = 3
        MIN_ACTION_LENGTH = 4  # Avoid matching very short strings

        if len(self.action_history) < MIN_ACTIONS_FOR_PATTERN:
            return ""
        a1, a2, a3 = self.action_history[-1], self.action_history[-2], self.action_history[-3]
        if a1 == a2 == a3 and len(a1) > MIN_ACTION_LENGTH:
            self.last_suggestion_time = time.time()
            return a1
        return ""

    def set_active_goal(self, goal: str):
        self.active_goal = goal
        self.set_preference("active_goal", goal)

    def get_active_goal(self) -> str:
        return self.active_goal or ""

    def clear_active_goal(self):
        self.active_goal = None
        if "active_goal" in self.prefs:
            del self.prefs["active_goal"]
        self._save()
        log.info("🎯 Active goal cleared.")
