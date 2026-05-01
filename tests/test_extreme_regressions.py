from security.security_core import ThreatAssessor
from tools.mirofish_simulator import MiroFishSimulator
from tools.pencil_swarm_agent import PencilSwarmAgent


def test_threat_assessor_marks_safe_os_actions_as_low_risk():
    assessor = ThreatAssessor()

    assert assessor.assess("open notepad").label == "LOW"
    assert assessor.assess("whatsapp kholo").label == "LOW"
    assert assessor.assess("hi pihu").label == "SAFE"


def test_mirofish_legacy_pattern_prediction_is_no_api_path():
    result = MiroFishSimulator()._pattern_prediction("stock market trend for nifty")

    assert "MiroFish" in result
    assert "CONSENSUS" in result


def test_swarm_planner_has_deterministic_fallback_when_llms_are_offline():
    agent = PencilSwarmAgent.__new__(PencilSwarmAgent)
    agent.groq = None
    agent.llm = None

    plan = agent._create_plan("Open notepad and type hello world")

    assert plan == [
        {
            "phase": "Deterministic OS fallback",
            "actions": [
                {"action": "open", "arg": "notepad"},
                {"action": "wait", "arg": "5"},
                {"action": "type", "arg": "hello world"},
            ],
            "verify": "",
        }
    ]
