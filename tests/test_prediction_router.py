from intent_classifier import Intent
from router import RouteResult, Router


def test_router_dispatches_prediction_intent_to_prediction_handler():
    router = Router.__new__(Router)
    router.voice_os = None
    router.memory = None
    router.confidence_threshold = 0.6
    router._route_prediction = lambda intent: RouteResult(
        pipeline="prediction",
        response=iter(["prediction ok"]),
        tool_announcement="",
    )

    result = router.route(Intent("prediction", 0.95, {}, "predict nifty trend"))

    assert result.pipeline == "prediction"
    assert "".join(result.response) == "prediction ok"


def test_prediction_route_sets_scenario_and_streams_mirofish(monkeypatch):
    import tools.mirofish_simulator as mirofish_module

    class FakeMiroFish:
        def predict_stream(self, query, data_context="", scenario="neutral"):
            yield f"{scenario}:{query}"

    monkeypatch.setattr(mirofish_module, "MiroFishSimulator", FakeMiroFish)

    router = Router.__new__(Router)
    result = router._route_prediction(Intent("prediction", 1.0, {}, "predict market downside risk"))

    assert result.pipeline == "prediction"
    assert result.metadata["scenario"] == "bearish"
    assert "".join(result.response) == "bearish:predict market downside risk"
