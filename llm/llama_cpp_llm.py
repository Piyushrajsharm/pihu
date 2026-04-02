"""
Pihu — Direct Llama.cpp Engine
Direct GGUF loading via llama-cpp-python.
NO background service (Ollama) required.
"""

import time
from typing import Generator, Optional
from pathlib import Path

from logger import get_logger

log = get_logger("LLM-NATIVE")


class LlamaCppLLM:
    """Direct GGUF inference engine."""

    def __init__(self, scheduler=None):
        from config import (
            LOCAL_MODEL_PATH, LOCAL_LLM_TEMPERATURE,
            LOCAL_LLM_MAX_TOKENS,
        )
        try:
            from llama_cpp import Llama
            
            model_path = Path(LOCAL_MODEL_PATH)
            if not model_path.exists():
                log.info("🏠 Local model check: Local GGUF not found (Mode: Cloud Fallback Active)")
                self.llm = None
                self.is_available = False
                return

            log.info("🧠 Loading native model: %s...", model_path.name)
            t0 = time.time()
            
            # Initialization (CPU optimized)
            self.llm = Llama(
                model_path=str(model_path),
                n_ctx=2048,           # Context window
                n_threads=4,          # Match common laptop CPU cores
                n_gpu_layers=0,       # CPU only (no compiler check)
                verbose=False
            )
            
            log.info("✅ Native model loaded in %.1fs", time.time() - t0)
            
        except ImportError:
            log.error("❌ llama-cpp-python not installed. Run 'pip install llama-cpp-python'")
            self.llm = None
        except Exception as e:
            log.error("❌ Failed to load native model: %s", e)
            self.llm = None

        self.temperature = LOCAL_LLM_TEMPERATURE
        self.max_tokens = LOCAL_LLM_MAX_TOKENS
        self.scheduler = scheduler
        self.is_available = self.llm is not None

    def check_models(self) -> dict[str, bool]:
        """Check if the local GGUF file exists."""
        from config import LOCAL_MODEL_PATH
        exists = Path(LOCAL_MODEL_PATH).exists()
        log.info("Native model status: %s", "✅ Ready" if exists else "❌ Missing")
        return {LOCAL_MODEL_PATH: exists}

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
    ) -> Generator[str, None, None] | str:
        """Generate response from the direct GGUF model."""
        if not self.llm:
            return "Piyush, mera model load nahi ho pa raha. Ek baar check karlo please."

        max_tok = max_tokens_override or self.max_tokens
        
        # Format for Phi-3.5
        formatted_prompt = f"<|system|>\n{system_prompt}<|end|>\n<|user|>\n{prompt}<|end|>\n<|assistant|>\n"

        t0 = time.time()
        
        try:
            if stream:
                return self._stream_generate(formatted_prompt, max_tok, t0)
            else:
                response = self.llm(
                    formatted_prompt,
                    max_tokens=max_tok,
                    temperature=self.temperature,
                    stop=["<|end|>", "<|user|>", "<|system|>"]
                )
                text = response["choices"][0]["text"]
                log.info("🧠 Native generation complete (batch) in %.1fs", time.time() - t0)
                return text
        except Exception as e:
            log.error("Native generation failed: %s", e)
            return f"Oops, error aa gaya native mode mein: {e}"

    def _stream_generate(self, prompt: str, max_tok: int, t0: float) -> Generator[str, None, None]:
        """Streaming token generation."""
        first_token_logged = False
        
        stream = self.llm(
            prompt,
            max_tokens=max_tok,
            temperature=self.temperature,
            stream=True,
            stop=["<|end|>", "<|user|>", "<|system|>"]
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
