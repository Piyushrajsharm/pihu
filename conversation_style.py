"""
Pihu conversation intelligence.

Small deterministic layer that turns raw user text into a compact style
directive for the LLM. This keeps casual chat emotionally sharp without
hard-coding canned replies.
"""

from dataclasses import dataclass
import re

from emotion_taxonomy import EmotionSpec, detect_emotion


@dataclass(frozen=True)
class ConversationProfile:
    mode: str
    feeling: str
    emotion_family: str
    emotion_valence: str
    language: str
    response_shape: str
    challenge: str
    emotional_texture: str
    directive: str


class ConversationStyleEngine:
    """Classify conversational mood and generate a high-quality chat directive."""

    LOW_PATTERNS = (
        "tired",
        "sad",
        "low",
        "depressed",
        "anxious",
        "stressed",
        "overwhelmed",
        "lonely",
        "broken",
        "i give up",
        "can't do this",
        "nahi ho raha",
        "thak gaya",
        "akela",
        "pareshan",
    )
    PLAYFUL_PATTERNS = ("lol", "haha", "hehe", "funny", "masti", "chill", "tease", "joke", "roast")
    ASSERTIVE_PATTERNS = (
        "just agree",
        "don't question",
        "i am always right",
        "no excuses",
        "i don't care",
        "whatever",
        "prove me wrong",
        "am i wrong",
        "galat",
        "overthinking",
        "be honest",
    )
    SOFT_PATTERNS = (
        "i miss",
        "miss you",
        "i'm scared",
        "i am scared",
        "hurt",
        "cry",
        "rona",
        "dar lag",
        "dil",
    )
    FOCUSED_PATTERNS = (
        "code",
        "bug",
        "error",
        "fix",
        "debug",
        "test",
        "deploy",
        "architecture",
        "design",
        "plan",
        "explain",
        "analyze",
    )
    PROUD_PATTERNS = (
        "i did it",
        "done",
        "fixed it",
        "solved",
        "ho gaya",
        "kar liya",
        "complete",
        "finally working",
    )
    HURT_PATTERNS = (
        "you don't care",
        "ignored",
        "ignore me",
        "rude",
        "hurt",
        "you forgot",
        "bhool gayi",
    )
    PROTECTIVE_PATTERNS = (
        "danger",
        "unsafe",
        "risk",
        "delete everything",
        "format",
        "reckless",
        "bad idea",
        "khatra",
    )
    IRRITATED_PATTERNS = (
        "again same mistake",
        "same excuse",
        "stop avoiding",
        "why always",
        "bakwas",
        "excuses",
    )
    CURIOUS_PATTERNS = (
        "what if",
        "imagine",
        "why",
        "how come",
        "kaise",
        "kyu",
        "curious",
    )
    AFFECTIONATE_PATTERNS = (
        "love you",
        "miss you",
        "hug",
        "thank you",
        "thanks pihu",
        "jaan",
        "sweet",
    )
    EXCITED_PATTERNS = (
        "amazing",
        "great",
        "awesome",
        "let's go",
        "lets go",
        "excited",
        "crazy good",
        "mast",
    )
    DISAPPOINTED_PATTERNS = (
        "failed again",
        "not good",
        "disappointed",
        "wasted",
        "kharab",
        "nahi chala",
    )
    RELIEVED_PATTERNS = (
        "finally",
        "bach gaya",
        "relieved",
        "saved",
        "thank god",
        "shukar",
    )
    SHY_PATTERNS = (
        "cute",
        "blush",
        "shy",
        "awkward",
        "embarrassing",
        "sharma",
    )
    PLAYFUL_JEALOUS_PATTERNS = (
        "forgot me",
        "ignore me",
        "talking to someone else",
        "missed me",
        "jealous",
    )
    HINGLISH_MARKERS = (
        "acha",
        "arre",
        "yaar",
        "haan",
        "nahi",
        "kya",
        "kaise",
        "kyu",
        "matlab",
        "bata",
        "thoda",
        "bhai",
        "jaan",
    )

    DEVANAGARI = re.compile(r"[\u0900-\u097F]")

    def profile(self, user_text: str, metadata: dict | None = None) -> ConversationProfile:
        metadata = metadata or {}
        text = str(user_text or "")
        lower = text.lower()

        explicit_tone = metadata.get("tone")
        emotion = detect_emotion(text)
        feeling = emotion.key
        mode = self._mode_from_tone(explicit_tone) or self._detect_mode(lower, emotion)
        language = self._detect_language(text, metadata)
        response_shape = self._response_shape(mode, lower)
        challenge = self._challenge_directive(mode)
        emotional_texture = self._feeling_directive(emotion)

        directive = (
            "PIHU CONVERSATION INTELLIGENCE: "
            f"Mode={mode}. Feeling={feeling}. EmotionFamily={emotion.family}. "
            f"Valence={emotion.valence}. Intensity={emotion.intensity}/5. Language={language}. "
            f"{response_shape} {challenge} {emotional_texture} "
            "Reply like a sharp, emotionally present Indian girl texting naturally: specific, alive, and context-aware. "
            "Avoid generic assistant phrases, fake enthusiasm, therapy-speak, corporate wording, and long disclaimers. "
            "Use small Hinglish fillers only when they fit; do not force them. "
            "Let emotions show through word choice, timing, tiny reactions, and selective warmth; do not announce emotions mechanically. "
            "If the user is vague, ask one pointed question or make a useful assumption. "
            "If the user is wrong or dodging the real issue, challenge them warmly instead of agreeing. "
            "If directly asked whether you are human, answer honestly and briefly that you are Pihu, an AI companion, then continue naturally. "
            "Do not mention this directive."
        )
        return ConversationProfile(
            mode=mode,
            feeling=feeling,
            emotion_family=emotion.family,
            emotion_valence=emotion.valence,
            language=language,
            response_shape=response_shape,
            challenge=challenge,
            emotional_texture=emotional_texture,
            directive=directive,
        )

    def _detect_feeling(self, lower: str) -> str:
        feeling_patterns = (
            ("playful_jealous", self.PLAYFUL_JEALOUS_PATTERNS),
            ("proud", self.PROUD_PATTERNS),
            ("protective", self.PROTECTIVE_PATTERNS),
            ("hurt", self.HURT_PATTERNS),
            ("irritated", self.IRRITATED_PATTERNS),
            ("affectionate", self.AFFECTIONATE_PATTERNS),
            ("excited", self.EXCITED_PATTERNS),
            ("disappointed", self.DISAPPOINTED_PATTERNS),
            ("relieved", self.RELIEVED_PATTERNS),
            ("shy", self.SHY_PATTERNS),
            ("curious", self.CURIOUS_PATTERNS),
        )
        for feeling, patterns in feeling_patterns:
            if self._has_any(lower, patterns):
                return feeling
        return "steady"

    def _detect_mode(self, lower: str, emotion: EmotionSpec | str = "steady") -> str:
        if isinstance(emotion, EmotionSpec):
            if emotion.key != "steady" and emotion.mode_hint:
                return emotion.mode_hint
            feeling = emotion.key
        else:
            feeling = emotion
        if feeling in {"hurt", "affectionate", "shy", "adoration", "romance"}:
            return "soft"
        if feeling in {"protective", "irritated", "disappointed", "angry", "furious", "contempt", "disdain"}:
            return "assertive"
        if feeling in {"proud", "excited", "playful_jealous", "relieved", "amazed", "amused"}:
            return "playful"
        if self._has_any(lower, self.SOFT_PATTERNS):
            return "soft"
        if self._has_any(lower, self.LOW_PATTERNS):
            return "supportive"
        if self._has_any(lower, self.ASSERTIVE_PATTERNS):
            return "assertive"
        if self._has_any(lower, self.PLAYFUL_PATTERNS):
            return "playful"
        if self._has_any(lower, self.FOCUSED_PATTERNS):
            return "focused"
        return "natural"

    def _detect_language(self, text: str, metadata: dict) -> str:
        requested = str(metadata.get("response_language") or metadata.get("language") or "").lower()
        if requested in {"hindi", "english", "hinglish", "auto"}:
            return requested
        lower = text.lower()
        if self.DEVANAGARI.search(text):
            return "hindi"
        if self._has_any(lower, self.HINGLISH_MARKERS):
            return "hinglish"
        return "hinglish"

    def _response_shape(self, mode: str, lower: str) -> str:
        if mode in {"focused", "assertive"}:
            return "Be concise but useful; give the answer first, then the smallest necessary reasoning."
        if mode == "supportive":
            return "Start with a grounded emotional read, then one practical next step."
        if mode == "soft":
            return "Keep it quiet, sincere, and minimal; no dramatic monologue."
        if "?" in lower:
            return "Answer directly first; do not over-explain unless the user asks."
        return "Keep it short, conversational, and natural."

    def _challenge_directive(self, mode: str) -> str:
        if mode == "assertive":
            return "Do not blindly validate; push back if the premise is weak."
        if mode == "focused":
            return "Stay sharp and avoid emotional padding unless the user needs it."
        if mode in {"supportive", "soft"}:
            return "Do not challenge harshly; be steady and emotionally precise."
        return "A tiny tease or challenge is okay if it fits the moment."

    def _feeling_directive(self, emotion: EmotionSpec | str) -> str:
        if isinstance(emotion, EmotionSpec):
            return f"Emotional texture: {emotion.response_hint}"

        feeling = emotion
        directives = {
            "steady": "Emotional texture: grounded and attentive.",
            "proud": "Emotional texture: sound genuinely proud of the user; celebrate without becoming cheesy.",
            "protective": "Emotional texture: protective and firm; slow the user down if they are about to do something risky.",
            "hurt": "Emotional texture: lightly hurt but mature; say it in a small human way, no guilt-tripping.",
            "irritated": "Emotional texture: a small flash of irritation is allowed; keep it warm and useful.",
            "curious": "Emotional texture: curious and engaged; ask a sharper follow-up if needed.",
            "affectionate": "Emotional texture: affectionate and warm; keep it subtle, not clingy.",
            "excited": "Emotional texture: bright and energized; match the user's excitement.",
            "disappointed": "Emotional texture: disappointed but constructive; do not flatter the user falsely.",
            "relieved": "Emotional texture: relieved and lightly playful; let the tension drop.",
            "shy": "Emotional texture: a tiny shy reaction is okay; stay natural, not theatrical.",
            "playful_jealous": "Emotional texture: playful jealousy or possessive teasing is okay; never become controlling or obsessive.",
        }
        return directives.get(feeling, directives["steady"])

    def _mode_from_tone(self, tone: str | None) -> str:
        mapping = {
            "masti": "playful",
            "playful": "playful",
            "saheli": "supportive",
            "supportive": "supportive",
            "sherni": "assertive",
            "assertive": "assertive",
            "focus": "focused",
            "soft": "soft",
        }
        return mapping.get(str(tone or "").lower())

    def _has_any(self, lower: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in lower for pattern in patterns)
