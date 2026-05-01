"""
Pihu - Groq LLM Engine
OpenAI-compatible GroqCloud provider used for fast planning and optional chat.
"""

import hashlib
import json
import time
from typing import Any, Generator, Optional

import requests

from logger import get_logger
from llm.base_provider import BaseProvider

log = get_logger("GROQ")


class GroqLLM(BaseProvider):
    """GroqCloud provider using the OpenAI-compatible chat completions API."""

    _AUTH_FAILED_KEY_HASHES: set[str] = set()

    def __init__(self):
        import config

        self.api_key = getattr(config, "GROQ_API_KEY", "")
        self._api_key_hash = self._hash_key(self.api_key)
        self.base_url = getattr(config, "GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
        self.model = getattr(config, "GROQ_MODEL", "llama-3.1-8b-instant")
        self.timeout = getattr(config, "GROQ_TIMEOUT_S", 10)
        self.max_tokens = getattr(config, "GROQ_MAX_TOKENS", 1024)
        self.temperature = getattr(config, "GROQ_TEMPERATURE", 0.35)
        self.top_p = getattr(config, "GROQ_TOP_P", 0.9)
        self._availability_checked = self._api_key_hash in self._AUTH_FAILED_KEY_HASHES
        self._api_key_valid = bool(self.api_key) and self._api_key_hash not in self._AUTH_FAILED_KEY_HASHES

        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=4,
            pool_maxsize=10,
            max_retries=requests.adapters.Retry(
                total=2,
                backoff_factor=0.35,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=frozenset({"GET", "POST"}),
            ),
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        if not self.api_key:
            log.warning("Groq API key not set - Groq provider unavailable")
        else:
            log.info("GroqLLM initialized | model=%s", self.model)

    @property
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        if not self._availability_checked:
            self.health_check()
        return self._api_key_valid

    def health_check(self) -> dict[str, Any]:
        """Verify Groq API reachability without exposing the API key."""
        if not self.api_key:
            self._availability_checked = True
            self._api_key_valid = False
            return {
                "available": False,
                "latency_ms": 0,
                "model_name": self.model,
                "error": "No API key",
            }

        t0 = time.time()
        try:
            response = self._session.get(
                f"{self.base_url}/models",
                headers=self._headers("application/json"),
                timeout=min(self.timeout, 8),
            )
            response.raise_for_status()
            latency = int((time.time() - t0) * 1000)
            self._availability_checked = True
            self._api_key_valid = True
            return {"available": True, "latency_ms": latency, "model_name": self.model}
        except Exception as exc:
            latency = int((time.time() - t0) * 1000)
            self._availability_checked = True
            self._api_key_valid = False
            log.warning("Groq health check failed: %s", exc)
            return {
                "available": False,
                "latency_ms": latency,
                "model_name": self.model,
                "error": str(exc),
            }

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Approximate cost for the default Groq Llama 3.1 8B model."""
        prompt_cost = (prompt_tokens / 1_000_000) * 0.05
        completion_cost = (completion_tokens / 1_000_000) * 0.08
        return prompt_cost + completion_cost

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
        if stream:
            return self.generate_stream(
                prompt,
                system_prompt,
                context,
                conversation_history,
                model_override,
                max_tokens_override,
                tools,
                stop_sequences,
            )
        return self.generate_batch(
            prompt,
            system_prompt,
            context,
            conversation_history,
            model_override,
            max_tokens_override,
            tools,
            stop_sequences,
        )

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
        if not self.is_available:
            return

        payload = self._build_payload(
            prompt,
            system_prompt,
            context,
            conversation_history,
            model_override,
            max_tokens_override,
            tools,
            stop_sequences,
            stream=True,
        )

        t0 = time.time()
        first_token_logged = False
        try:
            response = self._session.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers("text/event-stream"),
                json=payload,
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            self._mark_unavailable_on_auth_error(exc)
            log.warning("Groq stream connection failed: %s", exc)
            return

        try:
            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if not decoded.startswith("data: "):
                    continue
                data = decoded[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if not token:
                    continue
                if not first_token_logged:
                    log.info("Groq first token in %.0fms", (time.time() - t0) * 1000)
                    first_token_logged = True
                yield token
        except Exception as exc:
            log.warning("Groq stream interrupted: %s", exc)

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
        if not self.is_available:
            return None

        payload = self._build_payload(
            prompt,
            system_prompt,
            context,
            conversation_history,
            model_override,
            max_tokens_override,
            tools,
            stop_sequences,
            stream=False,
        )
        t0 = time.time()

        try:
            response = self._session.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers("application/json"),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            message = response.json().get("choices", [{}])[0].get("message", {})
            log.info("Groq batch response in %.0fms", (time.time() - t0) * 1000)
            if message.get("tool_calls"):
                return message
            return message.get("content", "")
        except Exception as exc:
            self._mark_unavailable_on_auth_error(exc)
            log.error("Groq batch failed: %s", exc)
            return None

    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        system_prompt: str = "",
    ) -> dict | str | None:
        system = (
            f"{system_prompt}\n\n"
            f"Return only a raw JSON object matching this schema: {json.dumps(schema)}"
        ).strip()
        result = self.generate_batch(prompt=prompt, system_prompt=system, max_tokens_override=self.max_tokens)
        if not result or not isinstance(result, str):
            return result

        clean = result.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return clean

    def _headers(self, accept: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": accept,
            "Content-Type": "application/json",
        }

    def _build_messages(
        self,
        prompt: str,
        system_prompt: str,
        context: Optional[list[str]],
        conversation_history: Optional[list[dict]],
    ) -> list[dict]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            context_text = "\n".join(f"- {item}" for item in context)
            messages.append({"role": "system", "content": f"Context:\n{context_text}"})
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_payload(
        self,
        prompt: str,
        system_prompt: str,
        context: Optional[list[str]],
        conversation_history: Optional[list[dict]],
        model_override: Optional[str],
        max_tokens_override: Optional[int],
        tools: Optional[list[dict]],
        stop_sequences: Optional[list[str]],
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_override or self.model,
            "messages": self._build_messages(prompt, system_prompt, context, conversation_history),
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": max_tokens_override or self.max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        if stop_sequences:
            payload["stop"] = stop_sequences
        return payload

    def _mark_unavailable_on_auth_error(self, exc: Exception) -> None:
        text = str(exc)
        if "401" in text or "403" in text or "Unauthorized" in text or "Forbidden" in text:
            self._availability_checked = True
            self._api_key_valid = False
            if self._api_key_hash:
                self._AUTH_FAILED_KEY_HASHES.add(self._api_key_hash)

    @staticmethod
    def _hash_key(api_key: str) -> str:
        if not api_key:
            return ""
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
