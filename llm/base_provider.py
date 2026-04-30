"""
Pihu — Base Model Provider Interface
Enforces a standard contract for all underlying LLM engines
supporting the Bring-Your-Own-Model (BYOM) architecture.
"""

from abc import ABC, abstractmethod
from typing import Generator, Optional, Any


class BaseProvider(ABC):
    """
    Abstract interface that all model backends (Local, Cloud, Ollama, etc.) must implement.
    """

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """
        Verify if the backend is reachable and the model is loaded.
        Returns metrics like latency and model name.
        """
        pass

    @abstractmethod
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
        """
        Primary inference routing hook. Automatically delegates to batch or stream.
        """
        pass

    @abstractmethod
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
        """
        Requires the backend to return tokens as strings progressively.
        """
        pass

    @abstractmethod
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
        """
        Requires the backend to return the complete response as a single string.
        """
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        system_prompt: str = "",
    ) -> dict | str | None:
        """
        Generates output guaranteed (or strongly prompted) to match JSON schema.
        Providers should implement local grammar constraints if supported.
        """
        pass

    @abstractmethod
    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Returns estimated usage cost. Returns 0.0 for local/free models.
        """
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Return True if initialized without errors."""
        pass
