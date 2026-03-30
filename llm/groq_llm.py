"""
Pihu — Groq LLM Engine
Ultra-fast inference (~100-200ms TTFT) via Groq's LPU hardware.
Used as PRIMARY for all chat — local Ollama is fallback only.
"""

import time
import json
import requests
from typing import Generator, Optional

from logger import get_logger

log = get_logger("GROQ")


class GroqLLM:
    """Groq cloud LLM — fastest inference available."""

    def __init__(self):
        from config import (
            GROQ_API_KEY, GROQ_MODEL,
            GROQ_TIMEOUT_S, GROQ_MAX_TOKENS,
        )

        self.api_key = GROQ_API_KEY
        self.model = GROQ_MODEL
        self.timeout = GROQ_TIMEOUT_S
        self.max_tokens = GROQ_MAX_TOKENS
        self.base_url = "https://api.groq.com/openai/v1"

        if not self.api_key:
            log.warning("⚠️ Groq API key not set — Groq unavailable")

        log.info("GroqLLM initialized | model=%s", self.model)

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        max_tokens_override: Optional[int] = None,
        context: list[str] | None = None,
        conversation_history: list[dict] | None = None,
    ) -> Generator[str, None, None] | str | None:
        """Generate response via Groq."""

        if not self.api_key:
            return None

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if context:
            context_text = "\n".join(f"- {c}" for c in context)
            messages.append({"role": "system", "content": f"Context:\n{context_text}"})

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": prompt})

        max_tok = max_tokens_override or self.max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tok,
            "temperature": 0.7,
            "stream": stream,
        }

        try:
            if stream:
                return self._stream_generate(headers, payload)
            else:
                return self._batch_generate(headers, payload)
        except Exception as e:
            log.error("Groq error: %s", e)
            return None

    def _stream_generate(self, headers: dict, payload: dict) -> Generator[str, None, None]:
        t0 = time.time()
        first_token_logged = False

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            log.warning("⚡ Groq connection failed (%.0fms): %s", (time.time() - t0) * 1000, e)
            return

        try:
            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                            token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if token:
                                if not first_token_logged:
                                    first_ms = (time.time() - t0) * 1000
                                    log.info("⚡ Groq first token in %.0fms", first_ms)
                                    first_token_logged = True
                                yield token
                        except json.JSONDecodeError:
                            continue
        except (ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
            log.warning("⚡ Groq stream interrupted: %s", e)
            return

        log.info("⚡ Groq complete in %.0fms", (time.time() - t0) * 1000)

    def _batch_generate(self, headers: dict, payload: dict) -> str:
        t0 = time.time()
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        log.info("⚡ Groq batch in %.0fms", (time.time() - t0) * 1000)
        return text
