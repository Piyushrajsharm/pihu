from pathlib import Path

from advanced_features import PihuAdvancedCore
from intent_classifier import Intent
from router import Router


def make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("Pihu advanced document RAG mission notes\n", "utf-8")
    (workspace / "app.py").write_text("print('hello')\n# TODO: improve\n", "utf-8")
    return workspace


def test_advanced_core_exposes_all_15_power_features(tmp_path):
    core = PihuAdvancedCore(make_workspace(tmp_path), user_id="tester")

    status = core.status()

    assert status["enabled"] is True
    assert status["feature_count"] == 15
    assert core.can_handle("advanced status")


def test_advanced_features_work_as_hardcoded_local_systems(tmp_path):
    workspace = make_workspace(tmp_path)
    core = PihuAdvancedCore(workspace, user_id="tester")

    mission = core.missions.create("monitor this repo and fix failing tests weekly")
    checkpoint = core.missions.checkpoint(mission["id"], "baseline captured")
    diagnosis = core.debugger.diagnose("AttributeError: 'CloudLLM' object has no attribute 'generate_sync'")
    plugin = core.plugins.register({
        "name": "Repo Watcher",
        "version": "1.0.0",
        "entrypoint": "repo_watcher:run",
        "permissions": ["read_repo"],
        "risk": "low",
    })
    screen = core.screen_memory.record("VS Code showed failing pytest output", window="VS Code", tags=["pytest"])
    simulation = core.simulator.simulate("open notepad and then type hello")
    risky_simulation = core.simulator.simulate("format c:")
    entity = core.knowledge_graph.add_entity("Pihu", "assistant", {"role": "AI companion"})
    edge = core.knowledge_graph.relate("Pihu", "helps", "Piyush")
    voice = core.interruptions.begin("utt-1", "hello")
    interrupted = core.interruptions.interrupt("correction")
    route = core.model_router.route("private local diary note", privacy="private")
    repo_scan = core.repo_guardian.scan(limit_files=20)
    skill = core.skills.learn("Open Notes", ["open notepad", "type hello"])
    reflection = core.reflection.reflect(["Piyush likes Python", "Piyush likes Python", "Piyush not likes noisy logs"])
    autonomy = core.autonomy.set_level("shell", "execute-with-confirmation")
    autonomy_decision = core.autonomy.decision("shell", "high")
    index = core.document_rag.index(workspace)
    search = core.document_rag.search("advanced RAG mission")
    evaluation = core.evaluation.run(core)
    live_ops = core.live_ops.snapshot(core, pipeline="advanced_core", metrics={"latency_ms": 1})

    assert mission["status"] == "active"
    assert checkpoint["note"] == "baseline captured"
    assert diagnosis["findings"][0]["code"] == "attribute_mismatch"
    assert plugin["enabled"] is True
    assert core.screen_memory.recall("pytest")[0]["id"] == screen["id"]
    assert simulation["risk"] == "low"
    assert risky_simulation["risk"] == "critical"
    assert entity["name"] == "Pihu"
    assert edge["relation"] == "helps"
    assert voice["speaking"] is True
    assert interrupted["paused"] is True
    assert route["selected"] == "local_llm"
    assert "grade" in repo_scan
    assert skill["verified"] is True
    assert reflection["duplicate_candidates"] == ["Piyush likes Python"]
    assert autonomy["level"] == "execute-with-confirmation"
    assert autonomy_decision["action"] == "ask_confirmation"
    assert index["indexed_files"] >= 2
    assert search and search[0]["citation"].endswith(":1")
    assert evaluation["passed"] == evaluation["total"] == 15
    assert live_ops["pipeline"] == "advanced_core"
    assert len(live_ops["features"]) == 15


def test_advanced_command_facade_and_router_pipeline(tmp_path):
    core = PihuAdvancedCore(make_workspace(tmp_path), user_id="tester")

    response = core.handle_command("mission: build a repo guardian")

    assert "build a repo guardian" in response

    router = Router.__new__(Router)
    router.voice_os = None
    router.advanced_core = core

    result = router.route(Intent("chat", 0.9, {}, "advanced status"))

    assert result.pipeline == "advanced_core"
    assert "feature_count" in "".join(result.response)
