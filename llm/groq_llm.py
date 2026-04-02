"""
Pihu — Groq LLM Engine (DEPRECATED)
This module is no longer in use.
"""

from logger import get_logger

log = get_logger("GROQ")


class GroqLLM:
    """Deprecated GroqLLM class."""

    def __init__(self):
        self.api_key = ""
        self.model = ""
        self.is_available = False
        log.warning("⚠️ GroqLLM is DEPRECATED and disabled in this version.")

    def generate(self, *args, **kwargs):
        log.error("Attempted to use deprecated GroqLLM.")
        return None
