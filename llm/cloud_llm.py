"""
Pihu — Cloud LLM Engine
NVIDIA NIM API integration with DeepSeek/Llama for heavy reasoning.
"""

import hashlib
import time
import requests
import json
from typing import Generator, Optional, Any

from logger import get_logger
from llm.base_provider import BaseProvider

log = get_logger("CLOUD")

class CloudLLM(BaseProvider):
    """Cloud LLM via NVIDIA NIM APIs (Synchronous Streaming).
    
    Uses connection pooling for improved performance and resource management.
    """

    _AUTH_FAILED_KEY_HASHES: set[str] = set()

    def __init__(self):
        import config
        self.api_key = getattr(config, "NVIDIA_NIM_API_KEY", "")
        self._api_key_hash = self._hash_key(self.api_key)
        self.base_url = getattr(config, "NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.model = getattr(config, "CLOUD_LLM_MODEL", "meta/llama-3.1-70b-instruct")
        self.vision_model = getattr(config, "CLOUD_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct")
        self.timeout = getattr(config, "CLOUD_LLM_TIMEOUT_S", 10)
        self.max_tokens = getattr(config, "CLOUD_LLM_MAX_TOKENS", 4096)
        self.temperature = getattr(config, "CLOUD_LLM_TEMPERATURE", 0.4)
        self.top_p = getattr(config, "CLOUD_LLM_TOP_P", 0.9)
        self._availability_checked = self._api_key_hash in self._AUTH_FAILED_KEY_HASHES
        self._api_key_valid = bool(self.api_key) and self._api_key_hash not in self._AUTH_FAILED_KEY_HASHES

        # Connection pooling for better performance
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=4,  # Number of connection pools to cache
            pool_maxsize=10,     # Maximum number of connections to save per pool
            max_retries=requests.adapters.Retry(
                total=2,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504]
            )
        )
        self._session.mount('https://', adapter)
        self._session.mount('http://', adapter)

        if not self.api_key:
            log.warning("⚠️ NVIDIA NIM API key not set — cloud LLM unavailable")

        log.info("CloudLLM initialized | model=%s, vision=%s", self.model, self.vision_model)

    @property
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        if not self._availability_checked:
            self.health_check()
        return self._api_key_valid

    def health_check(self) -> dict[str, Any]:
        """Verify network reachability of the cloud API."""
        if not self.api_key:
            self._availability_checked = True
            self._api_key_valid = False
            return {"available": False, "latency_ms": 0, "model_name": self.model, "error": "No API key"}
            
        t0 = time.time()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            # We hit the models endpoint for a quick ping
            res = self._session.get(f"{self.base_url}/models", headers=headers, timeout=5)
            res.raise_for_status()
            latency = int((time.time() - t0) * 1000)
            self._availability_checked = True
            self._api_key_valid = True
            return {"available": True, "latency_ms": latency, "model_name": self.model}
        except Exception as e:
            self._availability_checked = True
            self._api_key_valid = False
            return {"available": False, "latency_ms": int((time.time() - t0) * 1000), "model_name": self.model, "error": str(e)}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate usage costs. E.g., Llama 3 70B pricing."""
        # Typically $0.88 / 1M prompt, $0.88 / 1M completion on NVIDIA NIM
        return ((prompt_tokens + completion_tokens) / 1_000_000) * 0.88

    def _build_payload(self, prompt: str, system_prompt: str, context: Optional[list[str]], conversation_history: Optional[list[dict]], model_override: Optional[str], max_tokens_override: Optional[int], stream: bool):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        if context:
            context_text = "\n".join(f"- {c}" for c in context)
            messages.append({"role": "system", "content": f"Context:\n{context_text}"})
            
        if conversation_history:
            messages.extend(conversation_history)
            
        messages.append({"role": "user", "content": prompt})

        return {
            "model": model_override or self.model,
            "messages": messages,
            "max_tokens": max_tokens_override or self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": stream,
        }

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
    ) -> Generator[str, None, None] | str | None:
        """Primary router to batch or stream based on kwarg."""
        if stream:
            return self.generate_stream(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override)
        return self.generate_batch(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
    ) -> Generator[str, None, None]:
        if not self.is_available:
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream"
        }
        payload = self._build_payload(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, stream=True)
        t0 = time.time()
        first_token_logged = False

        try:
            response = self._session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.timeout
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self._mark_unavailable_on_auth_error(e)
            log.warning("☁️ Cloud connection failed: %s", e)
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
                                    log.info("☁️ Cloud first token in %.0fms", (time.time() - t0) * 1000)
                                    first_token_logged = True
                                yield token
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            log.warning("☁️ Cloud stream interrupted: %s", e)

    def generate_batch(
        self,
        prompt: str,
        system_prompt: str = "",
        context: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens_override: Optional[int] = None,
    ) -> str | None:
        if not self.is_available:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        payload = self._build_payload(prompt, system_prompt, context, conversation_history, model_override, max_tokens_override, stream=False)
        t0 = time.time()
        
        try:
            response = self._session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            log.info("☁️ Cloud batch response in %.0fms", (time.time() - t0) * 1000)
            return text
        except Exception as e:
            self._mark_unavailable_on_auth_error(e)
            log.error("☁️ Cloud batch failed: %s", e)
            return None

    def generate_structured(self, prompt: str, schema: dict, system_prompt: str = "") -> dict | str | None:
        """Use formatting prompt, as standard NIM doesn't strict-enforce raw JSON."""
        system = system_prompt + f"\n\nYou must return ONLY a raw JSON string matching this schema: {json.dumps(schema)}"
        # Call batch
        result = self.generate_batch(prompt=prompt, system_prompt=system)
        
        if not result:
            return None
            
        # Basic cleanup in case LLM wraps it in markdown blocks
        clean_result = result.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean_result)
        except json.JSONDecodeError:
            return clean_result

    def generate_vision(
        self,
        prompt: str,
        image_b64: str,
        system_prompt: str = "You are a spatial grounding assistant. Help me find UI elements.",
        stream: bool = False,
    ) -> str | None:
        """Cloud specific vision analyzer hook."""
        if not self.is_available:
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
            response = self._session.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            self._mark_unavailable_on_auth_error(e)
            log.error("Cloud Vision error: %s", e)
            return None

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
