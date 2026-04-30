import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from intent_classifier import Intent
from intent_classifier import IntentClassifier
from router import Router
from tools.voice_os_control import VoiceOSController


class FakeAutomation:
    def __init__(self):
        self.calls = []

    def _execute_single(self, action, arg, dry_run=False):
        self.calls.append((action, arg))
        return f"{action}:{arg}"

    def type_text(self, text):
        self.calls.append(("type", text))
        return f"type:{text}"

    def hotkey(self, *keys):
        self.calls.append(("hotkey", list(keys)))
        return "hotkey:" + "+".join(keys)

    def mouse_click(self, x, y):
        self.calls.append(("click", (x, y)))
        return f"click:{x},{y}"

    def find_and_click(self, target):
        self.calls.append(("find_and_click", target))
        return f"find:{target}"

    def scroll_mouse(self, amount):
        self.calls.append(("scroll", amount))
        return f"scroll:{amount}"

    def drag_and_drop(self, x1, y1, x2, y2):
        self.calls.append(("drag", (x1, y1, x2, y2)))
        return f"drag:{x1},{y1},{x2},{y2}"


def test_voice_os_opens_apps_from_spoken_command():
    automation = FakeAutomation()
    controller = VoiceOSController(automation=automation)

    result = controller.execute("Pihu, open notepad")

    assert result.success is True
    assert automation.calls == [("open", "notepad")]


def test_voice_os_types_and_presses_hotkeys():
    automation = FakeAutomation()
    controller = VoiceOSController(automation=automation)

    type_result = controller.execute("type Hello Pihu")
    press_result = controller.execute("press control plus s")

    assert type_result.success is True
    assert press_result.success is True
    assert automation.calls == [
        ("type", "Hello Pihu"),
        ("hotkey", ["ctrl", "s"]),
    ]


def test_voice_os_supports_simple_sequences():
    automation = FakeAutomation()
    controller = VoiceOSController(automation=automation)

    result = controller.execute("open notepad and type Hello")

    assert result.success is True
    assert automation.calls == [
        ("open", "notepad"),
        ("type", "Hello"),
    ]


def test_voice_os_requires_confirmation_for_shutdown():
    controller = VoiceOSController(dry_run=True)

    pending = controller.execute("shutdown pc")
    confirmed = controller.execute("confirm")

    assert pending.pending_confirmation is True
    assert "Confirm bolo" in pending.message
    assert confirmed.success is True
    assert "shutdown this PC" in confirmed.message


def test_router_routes_voice_os_before_interpreter():
    class FakeVoiceOS:
        def can_handle(self, text):
            return text == "open chrome"

        def execute(self, text):
            class Result:
                success = True
                pending_confirmation = False
                message = "opened chrome"

            return Result()

    router = Router.__new__(Router)
    router.backend_mode = False
    router.voice_os = FakeVoiceOS()

    result = router._route_system_command(Intent("system_command", 1.0, {}, "open chrome"))

    assert result.pipeline == "voice_os"
    assert "".join(result.response) == "opened chrome"


def test_router_voice_os_intercept_handles_plain_confirmation():
    class FakeVoiceOS:
        def can_handle(self, text):
            return text == "confirm"

        def execute(self, text):
            class Result:
                success = True
                pending_confirmation = False
                message = "confirmed"

            return Result()

    router = Router.__new__(Router)
    router.voice_os = FakeVoiceOS()

    result = router.route(Intent("chat", 0.8, {}, "confirm"))

    assert result.pipeline == "voice_os"
    assert "".join(result.response) == "confirmed"


def test_intent_classifier_recognizes_voice_os_shortcuts():
    classifier = IntentClassifier()

    assert classifier.classify("Pihu, press control s").type == "system_command"
    assert classifier.classify("open youtube").type == "system_command"
    assert classifier.classify("copy").type == "system_command"


def test_voice_os_handles_window_commands():
    automation = FakeAutomation()
    controller = VoiceOSController(automation=automation)

    result = controller.execute("maximize window")

    assert result.success is True
    assert automation.calls == [("hotkey", ["win", "up"])]


def test_voice_os_parses_mouse_drag_and_repeated_keys():
    controller = VoiceOSController(dry_run=True)

    drag = controller.execute("drag from 10 20 to 200 300")
    repeated = controller.execute("press down three times")

    assert drag.command.action == "drag"
    assert drag.command.arg == "10,20,200,300"
    assert repeated.command.action == "key_repeat"
    assert repeated.command.metadata["count"] == 3


def test_voice_os_opens_special_folders_and_paths(tmp_path):
    controller = VoiceOSController(dry_run=True, workspace_dir=tmp_path)

    project = controller.execute("open project")

    assert project.command.action == "open_path"
    assert project.command.arg == str(tmp_path.resolve())


def test_voice_os_searches_youtube():
    controller = VoiceOSController(dry_run=True)

    result = controller.execute("search youtube for pihu demo")

    assert result.command.action == "open_url"
    assert "youtube.com/results" in result.command.arg
    assert "pihu+demo" in result.command.arg


def test_voice_os_shell_uses_safety_gate_for_unknown_commands():
    controller = VoiceOSController(dry_run=True)

    pending = controller.execute("run command winget install something")
    confirmed = controller.execute("cancel")

    assert pending.pending_confirmation is True
    assert pending.command.action == "shell"
    assert confirmed.success is True


def test_intent_classifier_recognizes_advanced_voice_os_commands():
    classifier = IntentClassifier()

    assert classifier.classify("maximize window").type == "system_command"
    assert classifier.classify("run command echo hello").type == "system_command"
    assert classifier.classify("open downloads").type == "system_command"
