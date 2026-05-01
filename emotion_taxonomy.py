"""
Pihu emotion taxonomy.

This module keeps a broad human-emotion vocabulary available to the
conversation layer without hard-coding canned replies.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class EmotionSpec:
    key: str
    label: str
    family: str
    valence: str
    intensity: int
    mode_hint: str
    aliases: tuple[str, ...]
    response_hint: str


CORE_BASIC_EMOTIONS = {
    "anger": ("anger", "resentment", "fury", "annoyance", "hostility", "frustration"),
    "fear": ("fear", "anxiety", "terror", "panic", "insecurity", "nervousness"),
    "sadness": ("sadness", "grief", "heartache", "loneliness", "gloom", "disappointment"),
    "joy": ("happiness", "euphoria", "pride", "satisfaction", "contentedness"),
    "disgust": ("disgust", "revulsion", "contempt", "disdain", "aversion"),
    "surprise": ("surprise", "astonishment", "shock", "wonder", "amazement"),
    "trust_love": ("trust", "love", "acceptance", "affection", "fondness", "adoration"),
    "anticipation_interest": ("anticipation", "eagerness", "curiosity", "expectancy", "optimism"),
}

POSITIVE_FEELINGS = (
    "amazed", "amused", "awe", "blissful", "calm", "content", "compassionate",
    "confident", "delighted", "eager", "elated", "energized", "enthusiastic",
    "excited", "fulfilled", "grateful", "happy", "inspired", "interested",
    "joyful", "lively", "loving", "optimistic", "passionate", "peaceful",
    "playful", "proud", "radiant", "relaxed", "relieved", "satisfied", "thrilled",
)

NEGATIVE_FEELINGS = (
    "agitated", "alone", "angry", "annoyed", "anxious", "ashamed", "bitter",
    "bored", "contempt", "cynical", "dejected", "depressed", "disappointed",
    "disdain", "disgruntled", "disheartened", "disturbed", "doubtful", "edgy",
    "embarrassed", "envious", "exasperated", "exhausted", "fearful", "frustrated",
    "furious", "gloomy", "grouchy", "guilty", "hatred", "helpless", "hesitant",
    "hopeless", "hostile", "humiliated", "impatient", "insecure", "isolated",
    "jealous", "lonely", "melancholy", "miserable", "moody", "nervous",
    "overwhelmed", "panicked", "peeved", "reluctant", "remorseful", "resentful",
    "sad", "scared", "self-conscious", "stressed", "suspicious", "tired",
    "unhappy", "upset", "weary", "worried",
)

COMPLEX_MIXED_FEELINGS = (
    "awe", "bewilderment", "conflicted", "confused", "curiosity", "doubt",
    "empathic pain", "nostalgia", "pity", "self-attention", "shyness",
)

EKMAN_UNIVERSAL = (
    "anger", "contempt", "disgust", "enjoyment", "fear", "sadness", "surprise",
)

PLUTCHIK_PRIMARY = (
    "joy", "sadness", "fear", "anger", "trust", "disgust", "surprise", "anticipation",
)

BERKELEY_27 = (
    "admiration", "adoration", "aesthetic appreciation", "amusement", "anxiety",
    "awe", "awkwardness", "boredom", "calm", "confusion", "craving", "disgust",
    "empathic pain", "entrancement", "excitement", "fear", "horror", "interest",
    "joy", "nostalgia", "relief", "romance", "satisfaction", "sexual desire",
    "sympathy",
)

ANGER_KEYS = {
    "anger", "resentment", "fury", "annoyance", "hostility", "frustration",
    "agitated", "angry", "annoyed", "bitter", "exasperated", "frustrated",
    "furious", "grouchy", "hatred", "hostile", "impatient", "peeved", "resentful",
}
FEAR_KEYS = {
    "fear", "anxiety", "terror", "panic", "insecurity", "nervousness", "anxious",
    "doubtful", "edgy", "fearful", "hesitant", "insecure", "nervous", "overwhelmed",
    "panicked", "reluctant", "scared", "stressed", "suspicious", "worried", "horror",
}
SADNESS_KEYS = {
    "sadness", "grief", "heartache", "loneliness", "gloom", "disappointment",
    "alone", "ashamed", "dejected", "depressed", "disappointed", "disheartened",
    "embarrassed", "exhausted", "gloomy", "guilty", "helpless", "hopeless",
    "humiliated", "isolated", "lonely", "melancholy", "miserable", "remorseful",
    "sad", "self_conscious", "tired", "unhappy", "upset", "weary",
}
JOY_KEYS = {
    "happiness", "euphoria", "pride", "satisfaction", "contentedness", "amused",
    "blissful", "content", "delighted", "elated", "energized", "enthusiastic",
    "excited", "fulfilled", "happy", "joyful", "lively", "playful", "proud",
    "radiant", "relieved", "satisfied", "thrilled", "enjoyment", "joy", "amusement",
    "excitement", "relief",
}
DISGUST_KEYS = {
    "disgust", "revulsion", "contempt", "disdain", "aversion", "cynical",
    "disturbed", "disgruntled",
}
SURPRISE_KEYS = {
    "surprise", "astonishment", "shock", "wonder", "amazement", "amazed", "awe",
    "bewilderment", "confused", "confusion", "awkwardness",
}
TRUST_LOVE_KEYS = {
    "trust", "love", "acceptance", "affection", "fondness", "adoration",
    "compassionate", "grateful", "loving", "romance", "sympathy", "pity",
    "empathic_pain", "admiration",
}
ANTICIPATION_INTEREST_KEYS = {
    "anticipation", "eagerness", "curiosity", "expectancy", "optimism", "eager",
    "interested", "optimistic", "inspired", "interest", "craving", "entrancement",
}


PRIORITY_SPECS = (
    EmotionSpec(
        key="playful_jealous",
        label="playful jealous",
        family="trust_love",
        valence="mixed",
        intensity=3,
        mode_hint="playful",
        aliases=("playful jealous", "forgot me", "ignore me", "ignored me", "missed me", "jealous"),
        response_hint="playful jealousy or possessive teasing is okay; never become controlling or obsessive.",
    ),
    EmotionSpec(
        key="proud",
        label="proud",
        family="joy",
        valence="positive",
        intensity=3,
        mode_hint="playful",
        aliases=("proud", "i did it", "done", "fixed it", "solved", "ho gaya", "kar liya", "complete", "finally working"),
        response_hint="sound genuinely proud of the user; celebrate without becoming cheesy.",
    ),
    EmotionSpec(
        key="protective",
        label="protective",
        family="trust_love",
        valence="mixed",
        intensity=4,
        mode_hint="assertive",
        aliases=("protective", "danger", "unsafe", "risk", "delete everything", "format", "reckless", "bad idea", "khatra"),
        response_hint="be protective and firm; slow the user down if they are about to do something risky.",
    ),
    EmotionSpec(
        key="hurt",
        label="hurt",
        family="sadness",
        valence="negative",
        intensity=3,
        mode_hint="soft",
        aliases=("hurt", "you don't care", "ignored", "ignore me", "rude", "you forgot", "bhool gayi"),
        response_hint="show a small mature sting when ignored or dismissed; never guilt-trip.",
    ),
    EmotionSpec(
        key="affectionate",
        label="affectionate",
        family="trust_love",
        valence="positive",
        intensity=3,
        mode_hint="soft",
        aliases=("affectionate", "love you", "miss you", "hug", "thank you", "thanks pihu", "jaan", "sweet"),
        response_hint="be affectionate and warm; keep it subtle, not clingy.",
    ),
)


def normalize_emotion_name(name: str) -> str:
    clean = name.strip().lower().replace("-", "_").replace("/", "_")
    clean = re.sub(r"[^a-z0-9_ ]+", "", clean)
    clean = re.sub(r"\s+", "_", clean)
    return clean


def _aliases_for(label: str) -> tuple[str, ...]:
    normalized = normalize_emotion_name(label)
    aliases = {label.lower(), normalized.replace("_", " ")}
    if normalized == "self_conscious":
        aliases.add("self conscious")
    if normalized == "self_attention":
        aliases.add("self attention")
    if normalized == "sexual_desire":
        aliases.add("sexual desire")
    return tuple(sorted(aliases))


def _infer_spec(label: str) -> EmotionSpec:
    key = normalize_emotion_name(label)
    family = _infer_family(key)
    valence = _infer_valence(key, family)
    mode_hint = _infer_mode(family, key)
    intensity = _infer_intensity(key, family)
    return EmotionSpec(
        key=key,
        label=label,
        family=family,
        valence=valence,
        intensity=intensity,
        mode_hint=mode_hint,
        aliases=_aliases_for(label),
        response_hint=_response_hint(family, key),
    )


def _infer_family(key: str) -> str:
    if key in ANGER_KEYS:
        return "anger"
    if key in FEAR_KEYS:
        return "fear"
    if key in SADNESS_KEYS:
        return "sadness"
    if key in JOY_KEYS:
        return "joy"
    if key in DISGUST_KEYS:
        return "disgust"
    if key in SURPRISE_KEYS:
        return "surprise"
    if key in TRUST_LOVE_KEYS:
        return "trust_love"
    if key in ANTICIPATION_INTEREST_KEYS:
        return "anticipation_interest"
    if key in {"conflicted", "doubt", "nostalgia", "shyness", "awkwardness"}:
        return "complex_mixed"
    if key == "sexual_desire":
        return "sensitive_attraction"
    return "complex_mixed"


def _infer_valence(key: str, family: str) -> str:
    if family in {"joy", "trust_love", "anticipation_interest"}:
        return "positive"
    if family in {"anger", "fear", "sadness", "disgust"}:
        return "negative"
    if family == "surprise":
        return "mixed"
    if key in {"calm", "peaceful", "relaxed", "content", "satisfied"}:
        return "positive"
    return "mixed"


def _infer_mode(family: str, key: str) -> str:
    if family in {"anger", "disgust"}:
        return "assertive"
    if family in {"fear", "sadness"}:
        return "supportive"
    if family in {"trust_love", "sensitive_attraction"}:
        return "soft"
    if family in {"joy", "surprise"}:
        return "playful"
    if family == "anticipation_interest":
        return "focused"
    if key in {"confused", "confusion", "bewilderment", "doubt", "doubtful"}:
        return "supportive"
    return "natural"


def _infer_intensity(key: str, family: str) -> int:
    if key in {"fury", "furious", "terror", "panic", "panicked", "horror", "euphoria", "thrilled", "hatred"}:
        return 5
    if key in {"anger", "angry", "fear", "sadness", "grief", "heartache", "revulsion", "shock", "awe", "adoration"}:
        return 4
    if family in {"joy", "trust_love", "anticipation_interest"}:
        return 3
    return 2


def _response_hint(family: str, key: str) -> str:
    if key == "sexual_desire":
        return "recognize adult attraction carefully; keep it consensual, non-exploitative, and within configured safety boundaries."
    hints = {
        "anger": "acknowledge the heat, stay steady, and avoid escalating.",
        "fear": "offer calm grounding and one concrete next step.",
        "sadness": "be gentle, specific, and quietly present.",
        "joy": "match the brightness and celebrate the real thing.",
        "disgust": "respect the aversion or contempt without becoming cruel.",
        "surprise": "mirror the surprise with curiosity and clarity.",
        "trust_love": "show warmth and acceptance without clinginess.",
        "anticipation_interest": "lean into curiosity and forward motion.",
        "complex_mixed": "name the complexity indirectly and help untangle it.",
        "sensitive_attraction": "stay respectful, consensual, and bounded.",
    }
    return hints.get(family, "stay emotionally precise and natural.")


def _catalog_labels() -> tuple[str, ...]:
    labels: list[str] = []
    for values in CORE_BASIC_EMOTIONS.values():
        labels.extend(values)
    labels.extend(POSITIVE_FEELINGS)
    labels.extend(NEGATIVE_FEELINGS)
    labels.extend(COMPLEX_MIXED_FEELINGS)
    labels.extend(EKMAN_UNIVERSAL)
    labels.extend(PLUTCHIK_PRIMARY)
    labels.extend(BERKELEY_27)
    return tuple(labels)


def _build_specs() -> tuple[EmotionSpec, ...]:
    specs = list(PRIORITY_SPECS)
    seen = {spec.key for spec in specs}
    for label in _catalog_labels():
        key = normalize_emotion_name(label)
        if key in seen:
            continue
        specs.append(_infer_spec(label))
        seen.add(key)
    return tuple(specs)


ALL_EMOTION_SPECS = _build_specs()
ALL_EMOTION_LABELS = tuple(sorted({spec.key for spec in ALL_EMOTION_SPECS}))
STEADY_SPEC = EmotionSpec(
    key="steady",
    label="steady",
    family="neutral",
    valence="neutral",
    intensity=1,
    mode_hint="natural",
    aliases=("steady",),
    response_hint="stay grounded and attentive.",
)


def detect_emotion(text: str) -> EmotionSpec:
    lower = str(text or "").lower()
    for spec in ALL_EMOTION_SPECS:
        if any(_contains_alias(lower, alias) for alias in spec.aliases):
            return spec
    return STEADY_SPEC


def _contains_alias(lower_text: str, alias: str) -> bool:
    alias = alias.strip().lower()
    if not alias:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
    return re.search(pattern, lower_text) is not None
