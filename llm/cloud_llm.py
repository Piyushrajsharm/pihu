"""
Pihu — Cloud LLM Engine
NVIDIA NIM API integration with DeepSeek R1 for heavy reasoning.
Hard 4-second timeout with local fallback.
"""

import time
import requests
import json
from typing import Generator, Optional

from logger import get_logger

log = get_logger("CLOUD")

class CloudLLM:
    """Cloud LLM via NVIDIA NIM APIs (Synchronous Streaming)."""

    def __init__(self):
        import config
        from config import (
            NVIDIA_NIM_API_KEY, NVIDIA_NIM_BASE_URL,
            CLOUD_LLM_MODEL, CLOUD_LLM_TIMEOUT_S,
            CLOUD_LLM_MAX_TOKENS,
        )

        self.api_key = NVIDIA_NIM_API_KEY
        self.base_url = NVIDIA_NIM_BASE_URL
        self.model = CLOUD_LLM_MODEL
        self.vision_model = getattr(config, "CLOUD_VISION_MODEL", CLOUD_LLM_MODEL)
        self.timeout = CLOUD_LLM_TIMEOUT_S
        self.max_tokens = CLOUD_LLM_MAX_TOKENS

        if not self.api_key:
            log.warning("⚠️ NVIDIA NIM API key not set — cloud LLM unavailable")

        log.info("CloudLLM initialized | model=%s, vision=%s", self.model, self.vision_model)

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        context: list[str] | None = None,
        conversation_history: list[dict] | None = None,
    ) -> Generator[str, None, None] | str | None:
        """Generate response from cloud LLM synchronously."""
        
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

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream" if stream else "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 1.00,
            "top_p": 1.00,
            "stream": stream,
        }

        try:
            if stream:
                return self._stream_generate(headers, payload)
            else:
                return self._batch_generate(headers, payload)
        except Exception as e:
            log.error("Cloud LLM error: %s", e)
            return None

    def generate_vision(
        self,
        prompt: str,
        image_b64: str,
        system_prompt: str = "You are a spatial grounding assistant. Help me find UI elements.",
        stream: bool = False,
    ) -> str | None:
        """Analyze an image with cloud vision model."""
        if not self.api_key:
            return None

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            },
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }

        payload = {
            "model": self.vision_model,
            "messages": messages,
            "max_tokens": 1024,
            "stream": False,
        }

        try:
            return self._batch_generate(headers, payload)
        except Exception as e:
            log.error("Cloud Vision error: %s", e)
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
                timeout=self.timeout
            )
            response.raise_for_status()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            log.warning("☁️ Cloud connection failed (%.0fms): %s", (time.time() - t0) * 1000, e)
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
                                    log.info("☁️ Cloud first token in %.0fms", first_ms)
                                    first_token_logged = True
                                yield token
                        except json.JSONDecodeError:
                            continue
        except (ConnectionError, requests.exceptions.ChunkedEncodingError, 
                requests.exceptions.ConnectionError) as e:
            log.warning("☁️ Cloud stream interrupted (%.0fms): %s", (time.time() - t0) * 1000, e)
            return

        log.info("☁️ Cloud generation complete in %.0fms", (time.time() - t0) * 1000)

    def _batch_generate(self, headers: dict, payload: dict) -> str:
        t0 = time.time()
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        log.info("☁️ Cloud batch response in %.0fms", (time.time() - t0) * 1000)
        return text

    def generate_sync(self, prompt: str, system_prompt: str = "") -> str | None:
        """Alias for non-streaming."""
        return self.generate(prompt, system_prompt, stream=False)

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)
