"""
Pihu — Semantic Memory Layer
Stores persistent user preferences and recurring behaviors.
"""
import json
from pathlib import Path
from logger import get_logger

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
            self.failures.append(self.last_assistant_reply[:150]) # Prevent token bloat
            if len(self.failures) > 3: self.failures = self.failures[-3:] # Rolling limit
            log.warning("TaskState failure recorded: %s", self.last_assistant_reply[:50])
            self.last_assistant_reply = ""

    def get_context(self) -> str:
        if not self.active: return ""
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
    
    def __init__(self):
        from config import MEMORY_DIR
        from collections import deque
        self.prefs_file = Path(MEMORY_DIR) / "preferences.json"
        self._load()
        # Sliding action window for pattern automation
        self.action_history = deque(maxlen=10)
        self.active_goal = self.prefs.get("active_goal", None)
        self.last_suggestion_time = 0.0
        self.task_state = TaskState()
        self._init_mem0(MEMORY_DIR)

    def _init_mem0(self, mem_dir: str):
        try:
            from mem0 import Memory
            config = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": "pihu_memory_v3",
                        "path": str(Path(mem_dir) / "mem0_qdrant_v3")
                    }
                },
                "llm": {
                    "provider": "ollama",
                    "config": {
                        "model": "qwen2.5:3b",
                        "temperature": 0.0,
                    }
                },
                "embedder": {
                    "provider": "ollama",
                    "config": {
                        "model": "nomic-embed-text:latest",
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
            results = self.m.search(query, user_id="pihu_user", limit=3)
            if results:
                # Mem0 results are sometimes dicts, sometimes lists of dicts
                mem_strings = []
                for r in results:
                    if isinstance(r, dict):
                        # Safety: check for 'memory' or 'fact' keys
                        m = r.get("memory") or r.get("fact") or r.get("text", "")
                        if m: mem_strings.append(str(m))
                return " | ".join(mem_strings)
        except Exception as e:
            log.error("Mem0 search query failed: %s", e)
            
        return ""

    def update_memory_async(self, text: str):
        """Asynchronous Background Extraction (0 Latency)"""
        if not self._mem0_enabled or not text.strip():
            return
            
        import threading
        def _add():
            try:
                self.m.add(text, user_id="pihu_user")
            except Exception as e:
                log.error("Mem0 Background Extraction failed: %s", e)
                
        # Fire and forget
        threading.Thread(target=_add, daemon=True).start()

    def _load(self):
        self.prefs = {}
        if self.prefs_file.exists():
            try:
                self.prefs = json.loads(self.prefs_file.read_text("utf-8"))
            except json.JSONDecodeError:
                log.warning("Memory prefs file corrupted. Re-initializing empty prefs.")
                self.prefs = {}
            except Exception as e:
                log.error("Failed to load memory: %s", e)
                
    def _save(self):
        try:
            self.prefs_file.write_text(json.dumps(self.prefs, indent=2), "utf-8")
        except Exception as e:
            log.error("Failed to save memory: %s", e)

    def set_preference(self, key: str, value: str):
        self.prefs[key] = value
        
        # Macro Compression Logic (VRAM/Context bound protection)
        if len(self.prefs) > 15:
            log.warning("Memory saturation reached. Triggering inline trait compression.")
            keys = list(self.prefs.keys())
            if "active_goal" in keys: keys.remove("active_goal")
            over = len(keys) - 15
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
        """If last 3 actions are identical, propose macro via router."""
        import time
        if time.time() - self.last_suggestion_time < 3600:
            return "" # Throttle: Only suggest once per hour
            
        if len(self.action_history) < 3: 
            return ""
        a1, a2, a3 = self.action_history[-1], self.action_history[-2], self.action_history[-3]
        if a1 == a2 == a3 and len(a1) > 4:
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
