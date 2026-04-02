"""
Pihu — Local LLM Engine
Ollama integration with qwen2.5:3b (primary) and phi3:mini (fallback).
Supports streaming token generation.
"""

import time
from typing import Generator, Optional

from logger import get_logger

log = get_logger("LLM")


class LocalLLM:
    """Local LLM via Ollama.
    
    Primary: qwen2.5:3b (good balance of speed + quality)
    Fallback: phi3:mini (ultra-fast, lighter)
    Supports streaming for zero-latency pipeline.
    """

    def __init__(self, scheduler=None):
        from config import (
            OLLAMA_BASE_URL, LOCAL_LLM_PRIMARY,
            LOCAL_LLM_FALLBACK, LOCAL_LLM_TEMPERATURE,
            LOCAL_LLM_MAX_TOKENS,
        )
        import ollama

        self.client = ollama.Client(host=OLLAMA_BASE_URL)
        self.primary_model = LOCAL_LLM_PRIMARY
        self.fallback_model = LOCAL_LLM_FALLBACK
        self.temperature = LOCAL_LLM_TEMPERATURE
        self.max_tokens = LOCAL_LLM_MAX_TOKENS
        self.scheduler = scheduler
        self._current_model = self.primary_model

        log.info(
            "LocalLLM initialized | primary=%s, fallback=%s",
            self.primary_model, self.fallback_model,
        )

    def check_models(self) -> dict[str, bool]:
        """Check which models are available in Ollama."""
        available = {}
        try:
            models = self.client.list()
            model_names = [m.model for m in models.models] if hasattr(models, 'models') else []
            
            for target in [self.primary_model, self.fallback_model]:
                found = any(
                    target in name or name.startswith(target.split(":")[0])
                    for name in model_names
                )
                available[target] = found
                status = "✅" if found else "❌"
                log.info("Model %s: %s %s", target, status, "(available)" if found else "(not found)")

        except Exception as e:
            log.error("Cannot connect to Ollama: %s", e)
            available[self.primary_model] = False
            available[self.fallback_model] = False

        return available

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
    ) -> Generator[str, None, None] | str:
        """Generate a response from the local LLM.
        
        Args:
            prompt: User message
            system_prompt: System prompt (persona)
            stream: If True, yields tokens one by one
            model_override: Force a specific model
            max_tokens_override: Override max tokens (for short replies)

        Yields/Returns:
            Token strings (streaming) or full response string
        """
        model = model_override or self._get_model()
        max_tok = max_tokens_override or self.max_tokens

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()

        try:
            if stream:
                return self._stream_generate(model, messages, t0, max_tok)
            else:
                return self._batch_generate(model, messages, t0)

        except Exception as e:
            log.error("LLM generation failed with %s: %s", model, e)
            # Try fallback
            if model != self.fallback_model:
                log.info("Falling back to %s", self.fallback_model)
                self._current_model = self.fallback_model
                if stream:
                    return self._stream_generate(self.fallback_model, messages, t0, max_tok)
                else:
                    return self._batch_generate(self.fallback_model, messages, t0)
            raise

    def _stream_generate(
        self, model: str, messages: list, t0: float, max_tok: int = None
    ) -> Generator[str, None, None]:
        """Streaming token generation (with qwen3 think-tag filtering)."""
        first_token_logged = False
        num_predict = max_tok or self.max_tokens

        # TurboQuant optimization (KV cache compression)
        options = {
            "temperature": self.temperature,
            "num_predict": num_predict,
        }
        
        from config import TURBOQUANT_ENABLED
        if TURBOQUANT_ENABLED:
            # Enabling 4-bit KV cache quantization (TurboQuant behavior)
            # Note: requires Ollama 0.1.34+ or supporting backend
            options["kv_cache_type"] = "q4_0"
            log.info("🚀 TurboQuant Active: 4-bit KV Cache Compression enabled")

        response = self.client.chat(
            model=model,
            messages=messages,
            stream=True,
            options=options,
        )

        # Filter out <think>...</think> blocks (qwen3 "thinking" tokens)
        inside_think = False
        for chunk in response:
            token = chunk.get("message", {}).get("content", "")
            if not token:
                continue

            # Handle <think> tags that may span multiple tokens
            if "<think>" in token:
                inside_think = True
                # Keep anything before <think>
                before = token.split("<think>")[0]
                if before.strip():
                    yield before
                continue
            if "</think>" in token:
                inside_think = False
                # Keep anything after </think>
                after = token.split("</think>")[-1]
                if after.strip():
                    if not first_token_logged:
                        first_ms = (time.time() - t0) * 1000
                        log.info("⚡ First token in %.0fms | model=%s", first_ms, model)
                        first_token_logged = True
                    yield after
                continue
            if inside_think:
                continue

            # Normal token — yield it
            if not first_token_logged:
                first_ms = (time.time() - t0) * 1000
                log.info("⚡ First token in %.0fms | model=%s", first_ms, model)
                first_token_logged = True
            yield token

        total_ms = (time.time() - t0) * 1000
        log.info("🧠 Generation complete in %.0fms", total_ms)

    def _batch_generate(
        self, model: str, messages: list, t0: float
    ) -> str:
        """Non-streaming full response."""
        response = self.client.chat(
            model=model,
            messages=messages,
            stream=False,
            options={
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        )

        text = response.get("message", {}).get("content", "")
        elapsed_ms = (time.time() - t0) * 1000
        log.info(
            "🧠 Batch response in %.0fms | %d chars | model=%s",
            elapsed_ms, len(text), model,
        )
        return text

    def _get_model(self) -> str:
        """Get the recommended model based on scheduler state."""
        if self.scheduler:
            return self.scheduler.get_recommended_model()
        return self._current_model

    def generate_with_context(
        self,
        prompt: str,
        system_prompt: str,
        context: list[str],
        conversation_history: list[dict],
        stream: bool = True,
    ) -> Generator[str, None, None] | str:
        """Generate with memory context and conversation history.
        
        Args:
            prompt: Current user input
            system_prompt: Persona system prompt
            context: Retrieved memory context strings
            conversation_history: List of {"role": ..., "content": ...} dicts
            stream: Streaming mode
        """
        model = self._get_model()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Inject memory context
        if context:
            context_text = "\n".join(f"- {c}" for c in context)
            messages.append({
                "role": "system",
                "content": f"Relevant context from memory:\n{context_text}",
            })

        # Add conversation history
        messages.extend(conversation_history)

        # Add current prompt
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()

        try:
            if stream:
                return self._stream_generate(model, messages, t0)
            else:
                return self._batch_generate(model, messages, t0)
        except Exception as e:
            log.error("Contextual generation failed: %s", e)
            if model != self.fallback_model:
                self._current_model = self.fallback_model
                if stream:
                    return self._stream_generate(self.fallback_model, messages, t0)
                else:
                    return self._batch_generate(self.fallback_model, messages, t0)
            raise
