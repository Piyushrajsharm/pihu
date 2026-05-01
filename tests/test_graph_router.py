import pytest

from graph_router import GraphRouter
from intent_classifier import Intent


pytest.importorskip("langgraph")


class FakeLLM:
    is_available = True

    def __init__(self):
        self.calls = []

    def generate_batch(self, prompt, context=None):
        self.calls.append({"prompt": prompt, "context": context or []})
        return f"llm response: {prompt}"


class FakeMemory:
    def retrieve(self, text):
        return ["remembered context"]


def make_router(classifier=None, tools=None, llm=None):
    llm = llm or FakeLLM()
    router = GraphRouter(
        local_llm=llm,
        cloud_llm=None,
        intent_classifier=classifier,
        memory=FakeMemory(),
        tools_dict=tools or {},
    )
    assert router.is_available
    return router, llm


def test_graph_router_keeps_canonical_intent_and_deep_reasoning_out_of_tools():
    class Classifier:
        def classify(self, text):
            return Intent("deep_reasoning", 0.98, {}, text)

    router, llm = make_router(classifier=Classifier())

    result = router.execute("analyze this architecture deeply")

    assert result["intent"] == "deep_reasoning"
    assert result["pipeline"] == "langgraph"
    assert "No specific tool handled" not in llm.calls[-1]["prompt"]


def test_graph_router_route_matches_legacy_router_contract_without_reclassifying():
    class ExplodingClassifier:
        def classify(self, text):
            raise AssertionError("route() should reuse the provided Intent")

    router, _ = make_router(classifier=ExplodingClassifier())

    result = router.route(Intent("chat", 0.9, {}, "hello pihu"))

    assert result.pipeline == "langgraph"
    assert "".join(result.response).startswith("llm response")


def test_graph_router_composio_keyword_safety_net_covers_calendar_requests():
    class FakeComposio:
        is_available = True

        def __init__(self):
            self.prompts = []

        def execute(self, prompt):
            self.prompts.append(prompt)
            yield "calendar tool ok"

    composio = FakeComposio()
    router, _ = make_router(tools={"composio": composio})

    result = router.execute("please check my calendar tomorrow", intent=Intent("chat", 0.8, {}, "please check my calendar tomorrow"))

    assert result["pipeline"] == "composio"
    assert result["tool_results"] == ["calendar tool ok"]
    assert composio.prompts == ["please check my calendar tomorrow"]


def test_graph_router_tool_matrix_handles_voice_vision_and_prediction():
    class FakeVoiceOS:
        is_available = True

        def can_handle(self, text):
            return "notepad" in text

        def execute(self, text):
            class Result:
                message = "opened notepad"

            return Result()

    class FakeVision:
        is_available = True

        def analyze_screen(self, text):
            return "screen summary"

    class FakeMiroFish:
        def predict_stream(self, text):
            yield "prediction summary"

    router, _ = make_router(
        tools={
            "voice_os": FakeVoiceOS(),
            "vision": FakeVision(),
            "mirofish": FakeMiroFish(),
        }
    )

    system = router.execute("open notepad", intent=Intent("system_command", 1.0, {}, "open notepad"))
    vision = router.execute("look at the screen", intent=Intent("vision_analysis", 1.0, {}, "look at the screen"))
    prediction = router.execute("predict market risk", intent=Intent("prediction", 1.0, {}, "predict market risk"))

    assert system["pipeline"] == "voice_os"
    assert system["tool_results"] == ["opened notepad"]
    assert vision["pipeline"] == "vision"
    assert vision["tool_results"] == ["screen summary"]
    assert prediction["pipeline"] == "prediction"
    assert prediction["tool_results"] == ["prediction summary"]


def test_graph_router_routes_advanced_core_commands_before_generation():
    class FakeAdvancedCore:
        def can_handle(self, text):
            return "advanced status" in text

        def handle_command(self, text):
            return "advanced core ok"

    router, _ = make_router(tools={"advanced_core": FakeAdvancedCore()})

    result = router.route(Intent("chat", 0.9, {}, "advanced status"))

    assert result.pipeline == "advanced_core"
    assert "".join(result.response) == "advanced core ok"
