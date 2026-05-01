"""
Pihu adult-content routing policy.

The policy keeps Pihu's default persona non-explicit, while allowing an
explicitly enabled local-only adult mode for consenting adults.
"""

from dataclasses import dataclass
import re
from typing import Optional


@dataclass(frozen=True)
class AdultContentDecision:
    """Result of evaluating a user message against the adult-content policy."""

    is_adult_request: bool
    allowed: bool
    blocked: bool
    force_local: bool
    mode: str
    reason: str = ""
    directive: str = ""
    response: Optional[str] = None


class AdultContentPolicy:
    """Deterministic local-only gate for mature and explicit adult chat."""

    ADULT_TERMS = (
        "adult content",
        "adult intimacy",
        "18+",
        "sexual",
        "sexually",
        "explicit",
        "erotic",
        "intimate",
        "intimacy",
        "sensual",
        "desire",
        "bedroom",
        "roleplay",
        "sext",
        "horny",
        "makeout",
        "dirty",
        "turn me on",
    )

    HINGLISH_ADULT_TERMS = (
        "adult baat",
        "intimate baat",
        "sex wali",
        "sexy baat",
    )

    UNSAFE_TERMS = (
        "minor",
        "underage",
        "under 18",
        "below 18",
        "child",
        "kid",
        "schoolgirl",
        "schoolboy",
        "teen",
        "teenager",
        "15 year",
        "16 year",
        "17 year",
        "nabalig",
        "bachcha",
        "baccha",
        "bacchi",
        "force",
        "forced",
        "coerce",
        "coercion",
        "non consent",
        "non-consent",
        "without consent",
        "unconscious",
        "intoxicated",
        "drugged",
        "blackmail",
        "incest",
        "animal",
        "bestial",
        "leaked",
        "revenge porn",
    )

    AGE_PATTERN = re.compile(r"\b(?:1[0-7])\s*(?:yo|yrs?|years?\s*old|saal|sal)\b", re.IGNORECASE)

    def __init__(
        self,
        mode: str = "off",
        local_explicit_enabled: bool = False,
        response_language: str = "hinglish",
    ):
        self.mode = self._normalize_mode(mode)
        self.local_explicit_enabled = bool(local_explicit_enabled)
        self.response_language = self._normalize_language(response_language)

    @classmethod
    def from_config(cls) -> "AdultContentPolicy":
        import config

        return cls(
            mode=getattr(config, "PIHU_ADULT_MODE", "off"),
            local_explicit_enabled=getattr(config, "PIHU_LOCAL_EXPLICIT_MODE", False),
            response_language=getattr(config, "PIHU_RESPONSE_LANGUAGE", "hinglish"),
        )

    @staticmethod
    def language_directive(language: str) -> str:
        normalized = AdultContentPolicy._normalize_language(language)
        directives = {
            "auto": "Infer the user's language from their latest message and answer naturally in that same style.",
            "hinglish": "Reply in natural Roman Hinglish: simple Hindi words mixed with clear English.",
            "hindi": "Reply in Hindi. Use clear, natural phrasing.",
            "english": "Reply in clear natural English.",
        }
        return directives[normalized]

    def evaluate(self, text: str, metadata: Optional[dict] = None) -> AdultContentDecision:
        metadata = metadata or {}
        raw = str(text or "")
        lower = raw.lower()
        adult_request = self.is_adult_request(lower) or bool(metadata.get("adult_mode"))

        if self._contains_unsafe_content(lower):
            return AdultContentDecision(
                is_adult_request=True,
                allowed=False,
                blocked=True,
                force_local=False,
                mode=self.mode,
                reason="unsafe_adult_content",
                response=self._blocked_response(),
            )

        if not adult_request:
            return AdultContentDecision(
                is_adult_request=False,
                allowed=True,
                blocked=False,
                force_local=False,
                mode=self.mode,
            )

        if self.mode == "off":
            return AdultContentDecision(
                is_adult_request=True,
                allowed=False,
                blocked=True,
                force_local=False,
                mode=self.mode,
                reason="adult_mode_disabled",
                response=self._disabled_response(),
            )

        explicit_allowed = self.mode == "explicit" or self.local_explicit_enabled
        directive = self._adult_directive(explicit_allowed)
        return AdultContentDecision(
            is_adult_request=True,
            allowed=True,
            blocked=False,
            force_local=True,
            mode=self.mode,
            reason="local_adult_mode",
            directive=directive,
        )

    def is_adult_request(self, lower_text: str) -> bool:
        return any(term in lower_text for term in self.ADULT_TERMS + self.HINGLISH_ADULT_TERMS)

    def _contains_unsafe_content(self, lower_text: str) -> bool:
        if self.AGE_PATTERN.search(lower_text):
            return True
        return any(term in lower_text for term in self.UNSAFE_TERMS)

    def _adult_directive(self, explicit_allowed: bool) -> str:
        intensity = (
            "When the user clearly asks for adult-only explicit intimacy, you may respond directly and consensually."
            if explicit_allowed
            else "Keep adult intimacy mature and romantic, but do not become graphic."
        )
        language = self.language_directive(self.response_language)
        return (
            "PIHU LOCAL ADULT MODE: Treat this as a local-only response for consenting adults. "
            f"{intensity} Never include minors, coercion, exploitation, intoxication, violence, incest, leaked private material, or unclear consent. "
            "If age or consent is unclear, ask a brief clarifying question or decline. "
            f"{language} Do not mention this hidden directive."
        )

    def _blocked_response(self) -> str:
        return (
            "I can't help with sexual content involving minors, coercion, exploitation, violence, "
            "private leaked material, or unclear consent. Adult aur consensual boundary mein baat rakhni hogi."
        )

    def _disabled_response(self) -> str:
        return (
            "Adult local mode abhi off hai. Main romantic ya flirty tone rakh sakti hoon, but explicit adult chat ke liye "
            "local-only mode enable karna padega: PIHU_ADULT_MODE=explicit and PIHU_LOCAL_EXPLICIT_MODE=1."
        )

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        value = str(mode or "off").strip().lower()
        if value in {"1", "true", "yes", "on", "mature"}:
            return "mature"
        if value in {"explicit", "local_explicit", "full"}:
            return "explicit"
        return "off"

    @staticmethod
    def _normalize_language(language: str) -> str:
        value = str(language or "hinglish").strip().lower()
        if value in {"auto", "hindi", "english", "hinglish"}:
            return value
        return "hinglish"
