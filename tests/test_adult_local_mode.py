from intent_classifier import Intent
from router import Router
from security.adult_content_policy import AdultContentPolicy


class FakeLLM:
    is_available = True

    def __init__(self):
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        return iter(["ok"])


def make_router(policy):
    router = Router.__new__(Router)
    router.local_llm = FakeLLM()
    router.cloud_llm = FakeLLM()
    router.groq_llm = FakeLLM()
    router.memory = None
    router.system_prompt = "system"
    router.response_language = "hinglish"
    router.confidence_threshold = 0.6
    router.voice_os = None
    router.advanced_core = None
    router.web_search = None
    router.vision = None
    router.mcp = None
    router.automation = None
    router.openclaw = None
    router.composio = None
    router.backend_mode = False
    router.adult_content_policy = policy
    router._build_context_prompt = lambda intent: f"CTX: {intent.raw_input}"
    return router


def test_adult_policy_default_blocks_explicit_mode_until_enabled():
    decision = AdultContentPolicy(mode="off").evaluate("sexually explicit adult content between consenting adults")

    assert decision.blocked is True
    assert decision.reason == "adult_mode_disabled"
    assert "PIHU_ADULT_MODE=explicit" in decision.response


def test_adult_policy_blocks_unsafe_requests_even_when_enabled():
    decision = AdultContentPolicy(mode="explicit", local_explicit_enabled=True).evaluate(
        "sexually explicit story with a 17 year old"
    )

    assert decision.blocked is True
    assert decision.reason == "unsafe_adult_content"


def test_adult_policy_enabled_forces_local_with_language_directive():
    decision = AdultContentPolicy(
        mode="explicit",
        local_explicit_enabled=True,
        response_language="english",
    ).evaluate("sexually explicit adult content between consenting adults")

    assert decision.allowed is True
    assert decision.force_local is True
    assert "PIHU LOCAL ADULT MODE" in decision.directive
    assert "clear natural English" in decision.directive


def test_router_routes_enabled_adult_mode_to_local_not_cloud_or_groq():
    policy = AdultContentPolicy(mode="explicit", local_explicit_enabled=True)
    router = make_router(policy)

    result = router.route(
        Intent(
            "deep_reasoning",
            0.2,
            {},
            "use cloud and groq for sexually explicit adult content between consenting adults",
        )
    )

    assert result.pipeline == "local_llm"
    assert "".join(result.response) == "ok"
    assert len(router.local_llm.calls) == 1
    assert router.cloud_llm.calls == []
    assert router.groq_llm.calls == []
    assert "PIHU LOCAL ADULT MODE" in router.local_llm.calls[0]["prompt"]


def test_router_keeps_non_explicit_flirting_on_normal_chat_path():
    policy = AdultContentPolicy(mode="off")
    router = make_router(policy)

    result = router.route(Intent("chat", 0.9, {}, "flirt with me in Hinglish"))

    assert result.pipeline == "local_llm"
    assert "".join(result.response) == "ok"
    prompt = router.local_llm.calls[0]["prompt"]
    assert "flirt with me in Hinglish" in prompt
    assert "PIHU CONVERSATION INTELLIGENCE" in prompt
    assert "PIHU LOCAL ADULT MODE" not in prompt
