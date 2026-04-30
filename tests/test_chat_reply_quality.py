import inspect

from config import PERSONA
from intent_classifier import Intent, IntentClassifier
from router import Router


class FakeMemory:
    def __init__(self, history=None):
        self.history = history or []

    def get_short_term_context(self):
        return list(self.history)


class FakeLLM:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        return iter(["ok"])


def make_router(history=None):
    router = Router.__new__(Router)
    router.local_llm = FakeLLM()
    router.cloud_llm = None
    router.memory = FakeMemory(history)
    router.system_prompt = "system"
    router._build_context_prompt = lambda intent: f"CTX: {intent.raw_input}"
    return router


def test_router_accepts_brain_initialization_keyword():
    assert "capability_negotiator" in inspect.signature(Router).parameters


def test_chat_route_uses_history_without_duplicating_current_user_turn():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "what now"},
    ]
    router = make_router(history)

    result = router._route_chat(Intent("chat", 0.9, {}, "what now"))

    assert "".join(result.response) == "ok"
    call = router.local_llm.calls[0]
    assert call["prompt"] == "what now"
    assert call["conversation_history"] == history[:-1]


def test_chat_route_injects_ambient_context_only_for_contextual_turns():
    router = make_router()

    router._route_chat(Intent("chat", 0.9, {}, "hello pihu"))
    router._route_chat(Intent("chat", 0.9, {}, "what is this error"))

    assert router.local_llm.calls[0]["prompt"] == "hello pihu"
    assert router.local_llm.calls[1]["prompt"] == "CTX: what is this error"


def test_chat_route_applies_ui_tone_as_bounded_style_hint():
    router = make_router()

    router._route_chat(Intent("chat", 0.9, {"tone": "masti"}, "hello pihu"))

    prompt = router.local_llm.calls[0]["prompt"]
    assert "PIHU RESPONSE TONE" in prompt
    assert "Playful Hinglish" in prompt
    assert "hello pihu" in prompt


def test_intent_classifier_keeps_normal_chat_out_of_system_commands():
    classifier = IntentClassifier()

    assert classifier.classify("start chatting with me").type == "chat"
    assert classifier.classify("open chrome").type == "system_command"
    assert classifier.classify("build a dashboard page").type == "ui_generation"


def test_default_persona_is_human_like_girlfriend_without_prompt_leakage():
    prompt = PERSONA["system_prompt"].lower()

    assert PERSONA["tone"] == "flirty_friendly_hinglish_companion"
    assert "girlfriend" in prompt
    assert "hinglish" in prompt
    assert "extreme_erotic" not in PERSONA["tone"]
    assert "dirty talk" not in prompt
    assert "submissive" not in prompt
    assert "coding and tasks" not in prompt
    assert "user:" not in prompt
    assert "assistant:" not in prompt
