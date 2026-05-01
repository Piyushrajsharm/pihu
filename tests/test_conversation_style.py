from conversation_style import ConversationStyleEngine


def test_conversation_style_detects_supportive_hinglish_mode():
    profile = ConversationStyleEngine().profile("yaar main bahut stressed hoon")

    assert profile.mode == "supportive"
    assert profile.feeling == "stressed"
    assert profile.emotion_family == "fear"
    assert profile.emotion_valence == "negative"
    assert profile.language == "hinglish"
    assert "grounded emotional read" in profile.directive
    assert "generic assistant phrases" in profile.directive


def test_conversation_style_detects_assertive_mode_and_identity_boundary():
    profile = ConversationStyleEngine().profile("be honest, am I overthinking?")

    assert profile.mode == "assertive"
    assert profile.feeling == "steady"
    assert profile.emotion_family == "neutral"
    assert "push back" in profile.directive
    assert "If directly asked whether you are human" in profile.directive
    assert "AI companion" in profile.directive


def test_conversation_style_detects_focused_mode_for_debugging():
    profile = ConversationStyleEngine().profile("fix this Python error")

    assert profile.mode == "focused"
    assert profile.feeling == "steady"
    assert "give the answer first" in profile.directive
    assert "Stay sharp" in profile.directive


def test_conversation_style_adds_pride_and_relief_texture():
    profile = ConversationStyleEngine().profile("finally ho gaya, fixed it")

    assert profile.mode == "playful"
    assert profile.feeling == "proud"
    assert "genuinely proud" in profile.directive
    assert "Feeling=proud" in profile.directive


def test_conversation_style_adds_protective_assertive_texture():
    profile = ConversationStyleEngine().profile("format everything, I don't care about the risk")

    assert profile.mode == "assertive"
    assert profile.feeling == "protective"
    assert "protective and firm" in profile.directive


def test_conversation_style_adds_affectionate_soft_texture():
    profile = ConversationStyleEngine().profile("thanks pihu, miss you")

    assert profile.mode == "soft"
    assert profile.feeling == "affectionate"
    assert "affectionate and warm" in profile.directive


def test_conversation_style_adds_playful_jealous_texture_without_control():
    profile = ConversationStyleEngine().profile("you forgot me and ignored me")

    assert profile.mode == "playful"
    assert profile.feeling == "playful_jealous"
    assert "never become controlling or obsessive" in profile.directive
