from emotion_taxonomy import (
    ALL_EMOTION_LABELS,
    BERKELEY_27,
    CORE_BASIC_EMOTIONS,
    EKMAN_UNIVERSAL,
    PLUTCHIK_PRIMARY,
    detect_emotion,
)


def test_emotion_taxonomy_contains_requested_models_and_core_families():
    assert set(CORE_BASIC_EMOTIONS) == {
        "anger",
        "fear",
        "sadness",
        "joy",
        "disgust",
        "surprise",
        "trust_love",
        "anticipation_interest",
    }
    assert {"anger", "contempt", "disgust", "enjoyment", "fear", "sadness", "surprise"} <= set(EKMAN_UNIVERSAL)
    assert {"joy", "sadness", "fear", "anger", "trust", "disgust", "surprise", "anticipation"} <= set(PLUTCHIK_PRIMARY)
    assert "sexual desire" in BERKELEY_27


def test_emotion_taxonomy_contains_comprehensive_labels():
    required = {
        "resentment",
        "fury",
        "anxiety",
        "heartache",
        "euphoria",
        "revulsion",
        "astonishment",
        "adoration",
        "optimism",
        "self_attention",
        "empathic_pain",
        "aesthetic_appreciation",
        "sexual_desire",
    }

    assert required <= set(ALL_EMOTION_LABELS)


def test_emotion_taxonomy_detects_core_families_and_modes():
    assert detect_emotion("I am furious about this").family == "anger"
    assert detect_emotion("I am panicked and scared").family == "fear"
    assert detect_emotion("I feel lonely").family == "sadness"
    assert detect_emotion("That is pure contempt").family == "disgust"
    assert detect_emotion("I am amazed").family == "surprise"
    assert detect_emotion("I feel adoration").family == "trust_love"


def test_emotion_taxonomy_detects_sensitive_attraction_with_boundaries():
    spec = detect_emotion("sexual desire can be complicated")

    assert spec.key == "sexual_desire"
    assert spec.family == "sensitive_attraction"
    assert "consensual" in spec.response_hint
    assert "safety boundaries" in spec.response_hint
