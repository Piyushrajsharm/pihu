"""
Pihu — Direct Llama.cpp Engine
Direct GGUF loading via llama-cpp-python.
NO background service (Ollama) required.
"""

import time
import json
from typing import Generator, Optional, Any
from pathlib import Path

from logger import get_logger
from llm.base_provider import BaseProvider

log = get_logger("LLM-NATIVE")


class LlamaCppLLM(BaseProvider):
    """Direct GGUF inference engine."""

    def __init__(self, scheduler=None):
        from config import (
            LOCAL_MODEL_PATH, LOCAL_LLM_TEMPERATURE,
            LOCAL_LLM_MAX_TOKENS,
        )
        self.model_path = str(Path(LOCAL_MODEL_PATH))
        
        try:
            from llama_cpp import Llama
            
            p = Path(LOCAL_MODEL_PATH)
            if not p.exists():
                log.info("🏠 Local model check: Local GGUF not found (Mode: Cloud Fallback Active)")
                self.llm = None
                self._is_available = False
                return

            log.info("🧠 Loading native model: %s...", p.name)
            t0 = time.time()
            
            # Initialization (CPU optimized)
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=2048,           # Context window
                n_threads=4,          # Match common laptop CPU cores
                n_gpu_layers=0,       # CPU only (no compiler check)
                verbose=False
            )
            
            log.info("✅ Native model loaded in %.1fs", time.time() - t0)
            self._is_available = True
            
        except ImportError:
            log.error("❌ llama-cpp-python not installed. Run 'pip install llama-cpp-python'")
            self.llm = None
            self._is_available = False
        except Exception as e:
            log.error("❌ Failed to load native model: %s", e)
            self.llm = None
            self._is_available = False

        self.temperature = LOCAL_LLM_TEMPERATURE
        self.max_tokens = LOCAL_LLM_MAX_TOKENS
        self.scheduler = scheduler

    @property
    def is_available(self) -> bool:
        return getattr(self, "_is_available", False)

    def health_check(self) -> dict[str, Any]:
        """Check if the local GGUF file exists and model is loaded."""
        if not self.is_available:
            return {"available": False, "latency_ms": 0, "model_name": self.model_path, "error": "Model missing or llama-cpp-python not installed"}
        return {"available": True, "latency_ms": 0, "model_name": self.model_path}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Local execution is free."""
        return 0.0

    def _format_prompt(self, prompt: str, system_prompt: str, context: Optional[list[str]], conversation_history: Optional[list[dict]]) -> str:
        """Format for Phi-3.5 or fallback to generic."""
        system_text = system_prompt
        if context:
            system_text += "\nContext:\n" + "\n".join(f"- {c}" for c in context)
            
        # Very simple formatting matching old behavior
        formatted = f"<|system|>\n{system_text}<|end|>\n"
        
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                formatted += f"<|{role}|>\n{content}<|end|>\n"
                
        formatted += f"<|user|>\n{prompt}<|end|>\n<|assistant|>\n"
        return formatted

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> Generator[str, None, None] | str | None:
        """Generate response from the direct GGUF model."""
        if not self.is_available:
            return "Piyush, mera model load nahi ho pa raha. Ek baar check karlo please."

        if stream:
            return self.generate_stream(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, stop_sequences)
        return self.generate_batch(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, stop_sequences)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> Generator[str, None, None]:
        if not self.is_available:
            return
            
        formatted_prompt = self._format_prompt(prompt, system_prompt, context, conversation_history)
        max_tok = max_tokens_override or self.max_tokens
        t0 = time.time()
        first_token_logged = False
        
        try:
            stream = self.llm(
                formatted_prompt,
                max_tokens=max_tok,
                temperature=self.temperature,
                stream=True,
                stop=["<|end|>", "<|user|>", "<|system|>"] + (stop_sequences or [])
            )

            for chunk in stream:
                token = chunk["choices"][0]["text"]
                if token:
                    if not first_token_logged:
                        first_ms = (time.time() - t0) * 1000
                        log.info("⚡ Native first token in %.0fms", first_ms)
                        first_token_logged = True
                    yield token

            log.info("🧠 Native generation complete (stream) in %.1fs", time.time() - t0)
        except Exception as e:
            log.error("Native streaming failed: %s", e)

    def generate_batch(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> str | None:
        if not self.is_available:
            return None
            
        formatted_prompt = self._format_prompt(prompt, system_prompt, context, conversation_history)
        max_tok = max_tokens_override or self.max_tokens
        t0 = time.time()
        
        try:
            response = self.llm(
                formatted_prompt,
                max_tokens=max_tok,
                temperature=self.temperature,
                stop=["<|end|>", "<|user|>", "<|system|>"] + (stop_sequences or [])
            )
            text = response["choices"][0]["text"]
            log.info("🧠 Native generation complete (batch) in %.1fs", time.time() - t0)
            return text
        except Exception as e:
            log.error("Native generation failed: %s", e)
            return f"Oops, error aa gaya native mode mein: {e}"

    def generate_structured(self, prompt: str, schema: dict, system_prompt: str = "") -> dict | str | None:
        """Fallback to prompt-based structuring for CPU native."""
        sys = system_prompt + f"\n\nYou MUST return ONLY raw JSON matching exactly this schema: {json.dumps(schema)}"
        result = self.generate_batch(prompt, system_prompt=sys)
        if not result:
            return None
        clean = result.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return clean
