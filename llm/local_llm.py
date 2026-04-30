"""
Pihu — Local LLM Engine
Ollama integration with BYOM strategy.
Supports streaming token generation.
"""

import time
import json
from typing import Generator, Optional, Any

from logger import get_logger
from llm.base_provider import BaseProvider

log = get_logger("LLM")


class LocalLLM(BaseProvider):
    """Local LLM via Ollama."""

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
        self._is_available = True

        log.info(
            "LocalLLM initialized | primary=%s, fallback=%s",
            self.primary_model, self.fallback_model,
        )

    @property
    def is_available(self) -> bool:
        return self._is_available

    def health_check(self) -> dict[str, Any]:
        """Check which models are available in Ollama."""
        try:
            t0 = time.time()
            models = self.client.list()
            latency = int((time.time() - t0) * 1000)
            model_names = [m.model for m in models.models] if hasattr(models, 'models') else []
            
            found = any(
                self.primary_model in name or name.startswith(self.primary_model.split(":")[0])
                for name in model_names
            )
            return {"available": found, "latency_ms": latency, "model_name": self.primary_model}
        except Exception as e:
            self._is_available = False
            return {"available": False, "latency_ms": 0, "model_name": self.primary_model, "error": str(e)}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.0

    def _get_model(self) -> str:
        """Get the recommended model based on scheduler state."""
        if self.scheduler:
            return self.scheduler.get_recommended_model()
        return self._current_model

    def _build_messages(self, prompt: str, system_prompt: str, context: Optional[list[str]], conversation_history: Optional[list[dict]]) -> list[dict]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if context:
            context_text = "\n".join(f"- {c}" for c in context)
            messages.append({
                "role": "system",
                "content": f"Relevant context from memory:\n{context_text}",
            })

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> Generator[str, None, None] | str | dict | None:
        """Generate a response from the local LLM."""
        if tools and not stream:
            return self.generate_batch(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, tools, stop_sequences)
        
        if stream:
            return self.generate_stream(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, tools, stop_sequences)
        return self.generate_batch(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, tools, stop_sequences)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> Generator[str, None, None]:
        
        model = model_override or self._get_model()
        max_tok = max_tokens_override or self.max_tokens
        messages = self._build_messages(prompt, system_prompt, context, conversation_history)
        t0 = time.time()
        
        try:
            yield from self._stream_internal(model, messages, t0, max_tok, tools, stop_sequences)
        except Exception as e:
            log.error("LLM streaming failed with %s: %s", model, e)
            if model != self.fallback_model:
                log.info("Falling back to %s", self.fallback_model)
                try:
                    yield from self._stream_internal(self.fallback_model, messages, t0, max_tok, None, stop_sequences)
                    return
                except Exception:
                    pass
            yield f"⚠️ Pihu system is still waking up (Startup warm-up). Please wait a few seconds and try again. ({str(e)[:40]}...)"

    def _stream_internal(
        self,
        model: str,
        messages: list,
        t0: float,
        max_tok: int,
        tools: Optional[list] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> Generator[str, None, None]:
        options = {"temperature": self.temperature, "num_predict": max_tok}
        if stop_sequences:
            options["stop"] = stop_sequences
        
        from config import TURBOQUANT_ENABLED
        if TURBOQUANT_ENABLED:
            options["kv_cache_type"] = "q4_0"
            log.info("🚀 TurboQuant Active: 4-bit KV Cache Compression enabled")

        response = self.client.chat(
            model=model,
            messages=messages,
            stream=True,
            options=options,
            tools=tools
        )

        first_token_logged = False
        inside_think = False
        for chunk in response:
            token = chunk.get("message", {}).get("content", "")
            if not token: continue

            # Filter <think> blocks
            if "<think>" in token:
                inside_think = True
                before = token.split("<think>")[0]
                if before.strip(): yield before
                continue
            if "</think>" in token:
                inside_think = False
                after = token.split("</think>")[-1]
                if after.strip():
                    if not first_token_logged:
                        log.info("⚡ First token in %.0fms | model=%s", (time.time() - t0)*1000, model)
                        first_token_logged = True
                    yield after
                continue
            if inside_think: continue

            if not first_token_logged:
                log.info("⚡ First token in %.0fms | model=%s", (time.time() - t0)*1000, model)
                first_token_logged = True
            yield token

        log.info("🧠 Generation complete in %.0fms", (time.time() - t0)*1000)

    def generate_batch(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> str | dict | None:
        model = model_override or self._get_model()
        max_tok = max_tokens_override or self.max_tokens
        messages = self._build_messages(prompt, system_prompt, context, conversation_history)
        t0 = time.time()
        
        try:
            return self._batch_internal(model, messages, t0, max_tok, tools, stop_sequences)
        except Exception as e:
            log.error("LLM batch failed with %s: %s", model, e)
            if model != self.fallback_model:
                try:
                    return self._batch_internal(self.fallback_model, messages, t0, max_tok, None, stop_sequences)
                except:
                    pass
        return None

    def _batch_internal(
        self,
        model: str,
        messages: list,
        t0: float,
        max_tok: int,
        tools: Optional[list] = None,
        stop_sequences: Optional[list[str]] = None,
    ) -> str | dict:
        options = {
            "temperature": self.temperature,
            "num_predict": max_tok,
        }
        if stop_sequences:
            options["stop"] = stop_sequences

        response = self.client.chat(
            model=model,
            messages=messages,
            stream=False,
            options=options,
            tools=tools
        )
        msg = response.get("message", {})
        
        # If there's a tool call, return the whole message dict
        if msg.get("tool_calls"):
            log.info("🛠️ Tool call detected: %s", [tc['function']['name'] for tc in msg['tool_calls']])
            return msg

        text = msg.get("content", "")
        log.info("🧠 Batch response in %.0fms | chars=%d | model=%s", (time.time() - t0)*1000, len(text), model)
        return text

    def generate_structured(self, prompt: str, schema: dict, system_prompt: str = "") -> dict | str | None:
        """Ollama supports structured output format='json' directly."""
        sys = system_prompt + f"\n\nReturn EXACTLY a JSON object matching this schema: {json.dumps(schema)}"
        model = self._get_model()
        messages = self._build_messages(prompt, sys, None, None)
        
        try:
            response = self.client.chat(
                model=model,
                messages=messages,
                stream=False,
                format="json",  # Native Ollama JSON enforcement
                options={
                    "temperature": 0.1,  # Force determinism
                    "num_predict": self.max_tokens,
                },
            )
            text = response.get("message", {}).get("content", "")
            return json.loads(text)
        except Exception as e:
            log.error("JSON generation failed: %s", e)
            return None
