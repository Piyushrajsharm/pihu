"""
Pihu voice OS control.

Deterministic parser/executor for spoken desktop commands. This keeps common
voice-control actions fast and predictable instead of routing them through a
general code interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
import time
import webbrowser
from urllib.parse import quote_plus

from logger import get_logger

log = get_logger("VOICE-OS")


@dataclass
class VoiceOSCommand:
    action: str
    arg: str = ""
    keys: list[str] = field(default_factory=list)
    steps: list["VoiceOSCommand"] = field(default_factory=list)
    summary: str = ""
    risk: str = "safe"
    requires_confirmation: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class VoiceOSResult:
    handled: bool
    success: bool
    message: str
    command: VoiceOSCommand | None = None
    pending_confirmation: bool = False


class VoiceOSController:
    """Parse and execute spoken desktop-control commands."""

    CONFIRM_WORDS = {
        "confirm",
        "yes",
        "yes do it",
        "do it",
        "execute",
        "go ahead",
        "haan",
        "haan karo",
        "kar do",
        "pakka",
    }
    CANCEL_WORDS = {"cancel", "no", "stop", "mat karo", "rehne do", "nahi"}

    KEY_ALIASES = {
        "control": "ctrl",
        "ctrl": "ctrl",
        "alternate": "alt",
        "option": "alt",
        "escape": "esc",
        "esc": "esc",
        "windows": "win",
        "window": "win",
        "win": "win",
        "command": "win",
        "return": "enter",
        "enter": "enter",
        "space": "space",
        "spacebar": "space",
        "backspace": "backspace",
        "delete": "delete",
        "del": "delete",
        "tab": "tab",
        "shift": "shift",
        "capslock": "capslock",
        "caps lock": "capslock",
        "page up": "pageup",
        "page down": "pagedown",
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
        "home": "home",
        "end": "end",
        "print screen": "printscreen",
        "prtsc": "printscreen",
    }

    HOTKEY_PHRASES = {
        "copy": ["ctrl", "c"],
        "copy selected text": ["ctrl", "c"],
        "paste": ["ctrl", "v"],
        "paste clipboard": ["ctrl", "v"],
        "cut": ["ctrl", "x"],
        "select all": ["ctrl", "a"],
        "save": ["ctrl", "s"],
        "save file": ["ctrl", "s"],
        "undo": ["ctrl", "z"],
        "redo": ["ctrl", "y"],
        "new tab": ["ctrl", "t"],
        "close tab": ["ctrl", "w"],
        "reopen tab": ["ctrl", "shift", "t"],
        "refresh": ["ctrl", "r"],
        "reload": ["ctrl", "r"],
        "find": ["ctrl", "f"],
        "task manager": ["ctrl", "shift", "esc"],
        "show desktop": ["win", "d"],
        "minimize all": ["win", "d"],
        "switch window": ["alt", "tab"],
        "switch app": ["alt", "tab"],
        "next tab": ["ctrl", "tab"],
        "previous tab": ["ctrl", "shift", "tab"],
        "voice typing": ["win", "h"],
        "start dictation": ["win", "h"],
        "open notifications": ["win", "n"],
        "open quick settings": ["win", "a"],
        "open clipboard history": ["win", "v"],
        "open emoji panel": ["win", "."],
        "start menu": ["win"],
        "open start menu": ["win"],
        "screenshot": ["win", "shift", "s"],
        "take screenshot": ["win", "shift", "s"],
        "play pause": ["playpause"],
        "pause music": ["playpause"],
        "play music": ["playpause"],
        "next track": ["nexttrack"],
        "previous track": ["prevtrack"],
        "browser back": ["alt", "left"],
        "browser forward": ["alt", "right"],
        "go back": ["alt", "left"],
        "go forward": ["alt", "right"],
        "address bar": ["ctrl", "l"],
        "open address bar": ["ctrl", "l"],
        "delete word": ["ctrl", "backspace"],
        "go to start": ["home"],
        "go to end": ["end"],
    }

    WEBSITE_ALIASES = {
        "google": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "github": "https://github.com",
        "chatgpt": "https://chatgpt.com",
        "whatsapp web": "https://web.whatsapp.com",
        "linkedin": "https://www.linkedin.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "instagram": "https://www.instagram.com",
        "facebook": "https://www.facebook.com",
        "netflix": "https://www.netflix.com",
        "amazon": "https://www.amazon.in",
    }

    APP_ALIASES = {
        "browser": "chrome",
        "google chrome": "chrome",
        "explorer": "file explorer",
        "files": "file explorer",
        "file manager": "file explorer",
        "calc": "calculator",
        "vs code": "vscode",
        "visual studio code": "vscode",
        "power bi": "power bi",
        "command prompt": "cmd",
        "windows terminal": "terminal",
        "control panel": "control",
        "task manager": "taskmgr",
    }

    WINDOW_HOTKEYS = {
        "maximize window": ["win", "up"],
        "maximize": ["win", "up"],
        "minimize window": ["win", "down"],
        "minimize": ["win", "down"],
        "restore window": ["win", "down"],
        "snap left": ["win", "left"],
        "snap window left": ["win", "left"],
        "snap right": ["win", "right"],
        "snap window right": ["win", "right"],
        "move window left": ["win", "left"],
        "move window right": ["win", "right"],
        "open task view": ["win", "tab"],
    }

    SPECIAL_FOLDERS = {
        "desktop": "Desktop",
        "desktop folder": "Desktop",
        "downloads": "Downloads",
        "download": "Downloads",
        "downloads folder": "Downloads",
        "documents": "Documents",
        "documents folder": "Documents",
        "pictures": "Pictures",
        "photos folder": "Pictures",
        "music": "Music",
        "videos": "Videos",
        "home": "",
        "user folder": "",
    }

    NUMBER_WORDS = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }

    BLOCKED_TERMS = [
        "format",
        "delete system",
        "delete windows",
        "delete c drive",
        "rm -rf",
        "wipe",
        "factory reset",
        "uninstall",
    ]

    def __init__(
        self,
        automation=None,
        confirmation_ttl_s: float = 30.0,
        dry_run: bool = False,
        workspace_dir: str | os.PathLike | None = None,
    ):
        self.automation = automation
        self.confirmation_ttl_s = confirmation_ttl_s
        self.dry_run = dry_run
        self.workspace_dir = Path(workspace_dir).resolve() if workspace_dir else Path(__file__).resolve().parents[1]
        self._pending: VoiceOSCommand | None = None
        self._pending_at = 0.0

    def can_handle(self, spoken_text: str) -> bool:
        """Return True if the text looks like a voice OS command."""
        cleaned = self._clean(spoken_text)
        if not cleaned:
            return False
        if self._pending and self._is_pending_active():
            return self._is_confirmation(cleaned) or self._is_cancel(cleaned)
        return self.parse(spoken_text) is not None

    def execute(self, spoken_text: str) -> VoiceOSResult:
        """Parse and execute a spoken command, including confirmations."""
        cleaned = self._clean(spoken_text)
        if not cleaned:
            return VoiceOSResult(False, False, "Command empty tha.")

        if self._pending:
            if not self._is_pending_active():
                self._pending = None
                return VoiceOSResult(
                    True,
                    False,
                    "Confirmation timeout ho gaya. Command cancel kar diya.",
                )
            if self._is_cancel(cleaned):
                self._pending = None
                return VoiceOSResult(True, True, "Theek hai, command cancel kar diya.")
            if self._is_confirmation(cleaned):
                command = self._pending
                self._pending = None
                return self._execute_command(command, confirmed=True)

        command = self.parse(spoken_text)
        if command is None:
            return VoiceOSResult(
                False,
                False,
                f"Voice OS command samajh nahi aaya: '{spoken_text}'",
            )

        if command.requires_confirmation:
            self._pending = command
            self._pending_at = time.time()
            return VoiceOSResult(
                True,
                False,
                f"Confirm bolo to main yeh karungi: {command.summary}",
                command=command,
                pending_confirmation=True,
            )

        return self._execute_command(command)

    def parse(self, spoken_text: str) -> VoiceOSCommand | None:
        """Parse a spoken command into a deterministic action."""
        cleaned = self._clean(spoken_text)
        if not cleaned:
            return None

        sequence = self._parse_sequence(cleaned)
        if sequence:
            return sequence

        return self._parse_single(cleaned)

    def _parse_sequence(self, cleaned: str) -> VoiceOSCommand | None:
        if self._starts_with_literal_payload_command(cleaned):
            return None

        parts = re.split(
            r"\s+(?:and then|then|phir|uske baad|and)\s+"
            r"(?=(?:open|launch|start|run|kholo|khol|chalao|type|write|likho|"
            r"press|hit|click|scroll|focus|switch|close|search|google|wait|volume|"
            r"move|drag|right click|double click|maximize|minimize|snap|copy|paste|"
            r"select|shell|execute command)\b)",
            cleaned,
            flags=re.IGNORECASE,
        )
        parts = [part.strip() for part in parts if part.strip()]
        if len(parts) < 2:
            return None

        steps = []
        for part in parts:
            step = self._parse_single(part)
            if step is None:
                return None
            steps.append(step)

        summary = " -> ".join(step.summary for step in steps)
        return VoiceOSCommand(
            action="sequence",
            steps=steps,
            summary=summary,
            risk="medium" if any(step.risk != "safe" for step in steps) else "safe",
            requires_confirmation=any(step.requires_confirmation for step in steps),
        )

    def _parse_single(self, cleaned: str) -> VoiceOSCommand | None:
        low = cleaned.lower()

        if any(term in low for term in self.BLOCKED_TERMS):
            return VoiceOSCommand(
                action="blocked",
                arg=cleaned,
                summary=f"blocked destructive request: {cleaned}",
                risk="blocked",
            )

        power = self._parse_power_command(low)
        if power:
            return power

        shell = self._parse_shell(cleaned)
        if shell:
            return shell

        window = self._parse_window_command(low)
        if window:
            return window

        clipboard = self._parse_clipboard(low)
        if clipboard:
            return clipboard

        shortcut = self._parse_named_shortcut(low)
        if shortcut:
            return shortcut

        volume = self._parse_volume(low)
        if volume:
            return volume

        scroll = self._parse_scroll(low)
        if scroll:
            return scroll

        click = self._parse_click(cleaned)
        if click:
            return click

        mouse = self._parse_mouse_motion(cleaned)
        if mouse:
            return mouse

        typed = self._parse_type(cleaned)
        if typed:
            return typed

        pressed = self._parse_press(low)
        if pressed:
            return pressed

        wait = self._parse_wait(low)
        if wait:
            return wait

        screenshot = self._parse_screenshot(cleaned)
        if screenshot:
            return screenshot

        search = self._parse_search(cleaned)
        if search:
            return search

        path = self._parse_open_path(cleaned)
        if path:
            return path

        focus = self._parse_focus(cleaned)
        if focus:
            return focus

        open_target = self._parse_open(cleaned)
        if open_target:
            return open_target

        close = self._parse_close(low)
        if close:
            return close

        return None

    def _parse_power_command(self, low: str) -> VoiceOSCommand | None:
        if re.search(r"\b(shutdown|shut down|power off)\b", low):
            return VoiceOSCommand(
                action="system_power",
                arg="shutdown",
                summary="shutdown this PC",
                risk="high",
                requires_confirmation=True,
            )
        if re.search(r"\b(restart|reboot)\b", low):
            return VoiceOSCommand(
                action="system_power",
                arg="restart",
                summary="restart this PC",
                risk="high",
                requires_confirmation=True,
            )
        if re.search(r"\b(lock pc|lock computer|lock screen)\b", low):
            return VoiceOSCommand(
                action="system_power",
                arg="lock",
                summary="lock this PC",
                risk="medium",
                requires_confirmation=True,
            )
        if re.search(r"\b(sleep pc|sleep computer|put.*sleep)\b", low):
            return VoiceOSCommand(
                action="system_power",
                arg="sleep",
                summary="put this PC to sleep",
                risk="high",
                requires_confirmation=True,
            )
        return None

    def _parse_shell(self, cleaned: str) -> VoiceOSCommand | None:
        match = re.match(
            r"^(?:run command|execute command|shell command|terminal command|powershell command|cmd command)\s+(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if not match:
            return None

        command_text = match.group(1).strip()
        if not command_text:
            return None

        try:
            from security.command_classifier import CommandClassifier

            assessment = CommandClassifier().classify(command_text)
            if assessment.blocked or assessment.suggested_action == "deny":
                return VoiceOSCommand(
                    action="blocked",
                    arg=command_text,
                    summary=f"blocked shell command: {command_text}",
                    risk="blocked",
                )
            requires_confirmation = assessment.suggested_action in {"approval", "sandbox"}
            risk = assessment.risk_label.lower()
        except Exception as exc:
            log.warning("Shell command classifier unavailable: %s", exc)
            requires_confirmation = True
            risk = "high"

        return VoiceOSCommand(
            action="shell",
            arg=command_text,
            summary=f"run shell command '{command_text}'",
            risk=risk,
            requires_confirmation=requires_confirmation,
        )

    def _parse_window_command(self, low: str) -> VoiceOSCommand | None:
        for phrase, keys in self.WINDOW_HOTKEYS.items():
            if low == phrase or low == f"{phrase} karo":
                return VoiceOSCommand(
                    action="hotkey",
                    keys=keys,
                    summary=f"window action: {phrase}",
                )

        if low in {"active window", "current window", "which window", "what window"}:
            return VoiceOSCommand(
                action="active_window",
                summary="read active window title",
            )

        if low in {"list windows", "show windows", "open windows"}:
            return VoiceOSCommand(
                action="list_windows",
                summary="list open windows",
            )

        return None

    def _parse_clipboard(self, low: str) -> VoiceOSCommand | None:
        if low in {"read clipboard", "show clipboard", "what is copied", "clipboard"}:
            return VoiceOSCommand(
                action="clipboard_read",
                summary="read clipboard",
            )
        if low in {"clear clipboard", "empty clipboard"}:
            return VoiceOSCommand(
                action="clipboard_clear",
                summary="clear clipboard",
                risk="medium",
                requires_confirmation=True,
            )
        return None

    def _parse_named_shortcut(self, low: str) -> VoiceOSCommand | None:
        for phrase, keys in self.HOTKEY_PHRASES.items():
            if low == phrase or low == f"press {phrase}" or low == f"{phrase} karo":
                return VoiceOSCommand(
                    action="hotkey",
                    keys=keys,
                    summary=f"press {'+'.join(keys)}",
                )
        return None

    def _parse_volume(self, low: str) -> VoiceOSCommand | None:
        if "volume up" in low or "volume badha" in low:
            return VoiceOSCommand("hotkey", keys=["volumeup"], summary="increase volume")
        if "volume down" in low or "volume kam" in low:
            return VoiceOSCommand("hotkey", keys=["volumedown"], summary="decrease volume")
        if "mute" in low:
            return VoiceOSCommand("hotkey", keys=["volumemute"], summary="mute volume")
        return None

    def _parse_scroll(self, low: str) -> VoiceOSCommand | None:
        match = re.search(r"\bscroll\s+(up|down)\b(?:\s+(\d+))?", low)
        if not match:
            return None
        direction = match.group(1)
        clicks = int(match.group(2) or "5")
        amount = clicks if direction == "up" else -clicks
        return VoiceOSCommand(
            action="scroll",
            arg=str(amount),
            summary=f"scroll {direction}",
        )

    def _parse_click(self, cleaned: str) -> VoiceOSCommand | None:
        match = re.search(
            r"\b(right click|double click|middle click)(?:\s+at)?\s+(\d{1,5})\s*,?\s+(\d{1,5})\b",
            cleaned,
            re.IGNORECASE,
        )
        if match:
            click_type = match.group(1).lower().replace(" ", "_")
            x, y = match.group(2), match.group(3)
            return VoiceOSCommand(
                action=click_type,
                arg=f"{x},{y}",
                summary=f"{click_type.replace('_', ' ')} at {x},{y}",
            )

        match = re.search(r"\bclick(?:\s+at)?\s+(\d{1,5})\s*,?\s+(\d{1,5})\b", cleaned, re.IGNORECASE)
        if match:
            x, y = match.group(1), match.group(2)
            return VoiceOSCommand(
                action="click",
                arg=f"{x},{y}",
                summary=f"click at {x},{y}",
            )

        match = re.match(r"^(?:click|tap)\s+(.+)$", cleaned, re.IGNORECASE)
        if match:
            target = self._sanitize_target(match.group(1))
            if target:
                return VoiceOSCommand(
                    action="find_and_click",
                    arg=target,
                    summary=f"find and click {target}",
                )

        if cleaned.lower() in {"right click", "right-click"}:
            return VoiceOSCommand(
                action="right_click_current",
                summary="right click current pointer position",
            )

        if cleaned.lower() in {"double click", "double-click"}:
            return VoiceOSCommand(
                action="double_click_current",
                summary="double click current pointer position",
            )

        if cleaned.lower() in {"click", "tap"}:
            return VoiceOSCommand(
                action="click_current",
                summary="click current pointer position",
            )

        return None

    def _parse_mouse_motion(self, cleaned: str) -> VoiceOSCommand | None:
        match = re.search(
            r"\b(?:move mouse|move cursor|mouse)\s+(?:to|at)?\s*(\d{1,5})\s*,?\s+(\d{1,5})\b",
            cleaned,
            re.IGNORECASE,
        )
        if match:
            x, y = match.group(1), match.group(2)
            return VoiceOSCommand(
                action="move_mouse",
                arg=f"{x},{y}",
                summary=f"move mouse to {x},{y}",
            )

        match = re.search(
            r"\bdrag\s+(?:from\s+)?(\d{1,5})\s*,?\s+(\d{1,5})\s+(?:to|towards)\s+(\d{1,5})\s*,?\s+(\d{1,5})\b",
            cleaned,
            re.IGNORECASE,
        )
        if match:
            coords = ",".join(match.groups())
            return VoiceOSCommand(
                action="drag",
                arg=coords,
                summary=f"drag from {match.group(1)},{match.group(2)} to {match.group(3)},{match.group(4)}",
            )

        return None

    def _parse_type(self, cleaned: str) -> VoiceOSCommand | None:
        match = re.match(
            r"^(?:type|write|likho|likh|enter text)\s+(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if not match:
            return None
        text = match.group(1).strip()
        if not text:
            return None
        return VoiceOSCommand(
            action="type",
            arg=text,
            summary=f"type '{text[:40]}'",
        )

    def _parse_press(self, low: str) -> VoiceOSCommand | None:
        match = re.match(r"^(?:press|hit|dabao|key)\s+(.+)$", low)
        if not match:
            return None

        key_phrase = match.group(1)
        count = self._extract_count(key_phrase)
        if count > 1:
            key_phrase = re.sub(
                r"\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+times?$",
                "",
                key_phrase,
            ).strip()

        keys = self._parse_keys(key_phrase)
        if not keys:
            return None
        if len(keys) == 1 and count > 1:
            return VoiceOSCommand(
                action="key_repeat",
                keys=keys,
                summary=f"press {keys[0]} {count} times",
                metadata={"count": count},
            )
        return VoiceOSCommand(
            action="hotkey",
            keys=keys,
            summary=f"press {'+'.join(keys)}",
        )

    def _parse_wait(self, low: str) -> VoiceOSCommand | None:
        match = re.match(r"^(?:wait|ruk|ruko)\s+(\d+(?:\.\d+)?)", low)
        if not match:
            return None
        seconds = min(float(match.group(1)), 30.0)
        return VoiceOSCommand(
            action="wait",
            arg=str(seconds),
            summary=f"wait {seconds:g} seconds",
        )

    def _parse_screenshot(self, cleaned: str) -> VoiceOSCommand | None:
        if "screenshot" not in cleaned.lower():
            return None
        return VoiceOSCommand(
            action="screenshot",
            arg=cleaned,
            summary="take a screenshot/describe screen",
        )

    def _parse_search(self, cleaned: str) -> VoiceOSCommand | None:
        youtube_match = re.match(
            r"^(?:search youtube for|youtube search for|youtube)\s+(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if youtube_match:
            query = youtube_match.group(1).strip()
            if query:
                url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
                return VoiceOSCommand(
                    action="open_url",
                    arg=url,
                    summary=f"search YouTube for {query}",
                )

        match = re.match(
            r"^(?:search google for|google search for|google|search web for|search for)\s+(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if not match:
            return None
        query = match.group(1).strip()
        if not query:
            return None
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return VoiceOSCommand(
            action="open_url",
            arg=url,
            summary=f"search Google for {query}",
        )

    def _parse_open_path(self, cleaned: str) -> VoiceOSCommand | None:
        match = re.match(
            r"^(?:open|show|launch|go to)\s+(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if not match:
            return None

        target = self._sanitize_target(match.group(1))
        path = self._target_to_path(target)
        if path is None:
            return None

        return VoiceOSCommand(
            action="open_path",
            arg=str(path),
            summary=f"open {path}",
        )

    def _parse_focus(self, cleaned: str) -> VoiceOSCommand | None:
        match = re.match(
            r"^(?:focus|switch to|bring up|go to)\s+(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if not match:
            return None
        target = self._sanitize_target(match.group(1))
        if not target:
            return None
        return VoiceOSCommand(
            action="focus",
            arg=self._map_app(target),
            summary=f"focus {target}",
        )

    def _parse_open(self, cleaned: str) -> VoiceOSCommand | None:
        match = re.match(
            r"^(?:open|launch|start|run|kholo|khol|chalao|chala)\s+(.+)$",
            cleaned,
            re.IGNORECASE,
        )
        if not match:
            return None

        target = self._sanitize_target(match.group(1))
        if not target:
            return None

        url = self._target_to_url(target)
        if url:
            return VoiceOSCommand(
                action="open_url",
                arg=url,
                summary=f"open {target}",
            )

        app = self._map_app(target)
        return VoiceOSCommand(
            action="open",
            arg=app,
            summary=f"open {app}",
        )

    def _parse_close(self, low: str) -> VoiceOSCommand | None:
        if re.search(r"\b(close|band karo)\s+(?:current\s+)?(?:window|app)\b", low):
            return VoiceOSCommand(
                action="hotkey",
                keys=["alt", "f4"],
                summary="close current window",
                risk="medium",
            )
        match = re.match(r"^(?:close|band karo|band kar)\s+(.+)$", low)
        if match:
            target = self._sanitize_target(match.group(1))
            if target and target not in {"window", "app"}:
                return VoiceOSCommand(
                    action="close_app",
                    arg=self._map_app(target),
                    summary=f"close {target}",
                    risk="medium",
                    requires_confirmation=True,
                )
        return None

    def _execute_command(
        self,
        command: VoiceOSCommand,
        confirmed: bool = False,
    ) -> VoiceOSResult:
        if command.action == "blocked":
            return VoiceOSResult(
                True,
                False,
                "Yeh destructive command blocked hai. Main isko voice se execute nahi karungi.",
                command=command,
            )

        if command.requires_confirmation and not confirmed:
            return VoiceOSResult(
                True,
                False,
                f"Confirm bolo to main yeh karungi: {command.summary}",
                command=command,
                pending_confirmation=True,
            )

        if command.action == "sequence":
            messages = []
            ok = True
            for step in command.steps:
                result = self._execute_command(step, confirmed=confirmed)
                messages.append(result.message)
                ok = ok and result.success
                if not result.success:
                    break
            return VoiceOSResult(
                True,
                ok,
                "\n".join(messages),
                command=command,
            )

        if self.dry_run:
            return VoiceOSResult(
                True,
                True,
                f"[DRY RUN] {command.summary}",
                command=command,
            )

        try:
            message = self._dispatch(command, confirmed=confirmed)
            return VoiceOSResult(True, True, message, command=command)
        except Exception as exc:
            log.exception("Voice OS command failed: %s", command.summary)
            return VoiceOSResult(
                True,
                False,
                f"Voice OS action fail ho gaya: {exc}",
                command=command,
            )

    def _dispatch(self, command: VoiceOSCommand, confirmed: bool = False) -> str:
        if command.action == "open_url":
            webbrowser.open(command.arg)
            return f"Opened URL: {command.arg}"
        if command.action == "open_path":
            return self._open_path(command.arg)
        if command.action == "active_window":
            return self._get_active_window_title()
        if command.action == "list_windows":
            return self._list_windows()
        if command.action == "clipboard_read":
            return self._read_clipboard()
        if command.action == "clipboard_clear":
            return self._write_clipboard("")
        if command.action == "shell":
            return self._execute_shell(command.arg, confirmed=confirmed)
        if command.action == "system_power":
            return self._execute_power(command.arg, confirmed=confirmed)

        automation = self._get_automation()

        if command.action == "open":
            return automation._execute_single("open", command.arg)
        if command.action == "type":
            return automation.type_text(command.arg)
        if command.action == "hotkey":
            return automation.hotkey(*command.keys)
        if command.action == "key_repeat":
            return self._press_key_repeat(command.keys[0], int(command.metadata.get("count", 1)))
        if command.action == "click":
            x, y = [int(part.strip()) for part in command.arg.split(",", 1)]
            return automation.mouse_click(x, y)
        if command.action == "right_click":
            x, y = [int(part.strip()) for part in command.arg.split(",", 1)]
            return self._mouse_click(x, y, button="right")
        if command.action == "double_click":
            x, y = [int(part.strip()) for part in command.arg.split(",", 1)]
            return self._mouse_click(x, y, clicks=2)
        if command.action == "middle_click":
            x, y = [int(part.strip()) for part in command.arg.split(",", 1)]
            return self._mouse_click(x, y, button="middle")
        if command.action == "find_and_click":
            return automation.find_and_click(command.arg)
        if command.action == "focus":
            return automation._execute_single("focus", command.arg)
        if command.action == "close_app":
            focus_result = automation._execute_single("focus", command.arg)
            close_result = automation.hotkey("alt", "f4")
            return f"{focus_result}\n{close_result}"
        if command.action == "wait":
            time.sleep(float(command.arg))
            return f"Waited {command.arg}s"
        if command.action == "scroll":
            return automation.scroll_mouse(int(command.arg))
        if command.action == "drag":
            coords = [int(part.strip()) for part in command.arg.split(",")]
            return automation.drag_and_drop(*coords)
        if command.action == "screenshot":
            return automation._execute_single("screenshot", command.arg)
        if command.action == "click_current":
            import pyautogui

            pyautogui.click()
            return "Clicked current pointer position"
        if command.action == "right_click_current":
            import pyautogui

            pyautogui.click(button="right")
            return "Right clicked current pointer position"
        if command.action == "double_click_current":
            import pyautogui

            pyautogui.doubleClick()
            return "Double clicked current pointer position"
        if command.action == "move_mouse":
            x, y = [int(part.strip()) for part in command.arg.split(",", 1)]
            return self._move_mouse(x, y)

        raise ValueError(f"Unknown voice OS action: {command.action}")

    def _execute_power(self, action: str, confirmed: bool = False) -> str:
        if not confirmed:
            raise PermissionError("power action requires confirmation")
        if action == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", "0"])
            return "Shutdown command sent."
        if action == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", "0"])
            return "Restart command sent."
        if action == "lock":
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
            return "PC lock command sent."
        if action == "sleep":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return "Sleep command sent."
        raise ValueError(f"Unknown power action: {action}")

    def _execute_shell(self, command: str, confirmed: bool = False) -> str:
        try:
            from security.command_classifier import CommandClassifier

            assessment = CommandClassifier().classify(command)
            if assessment.blocked or assessment.suggested_action == "deny":
                return "Shell command blocked by safety classifier."
            if assessment.suggested_action in {"approval", "sandbox"} and not confirmed:
                raise PermissionError("shell command requires confirmation")
        except PermissionError:
            raise
        except Exception as exc:
            log.warning("Shell safety check failed before execution: %s", exc)
            if not confirmed:
                raise PermissionError("shell safety check failed; confirmation required")

        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        if len(output) > 1200:
            output = output[:1200].rstrip() + "\n...output truncated..."
        if completed.returncode != 0:
            return f"Command exited with code {completed.returncode}.\n{output}".strip()
        return output or "Command completed."

    def _open_path(self, path_text: str) -> str:
        path = Path(path_text).expanduser()
        if not path.exists():
            return f"Path not found: {path}"
        os.startfile(str(path))
        return f"Opened: {path}"

    def _press_key_repeat(self, key: str, count: int) -> str:
        import pyautogui

        count = max(1, min(count, 20))
        for _ in range(count):
            pyautogui.press(key)
        return f"Pressed {key} {count} times"

    def _mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> str:
        import pyautogui

        pyautogui.click(x=x, y=y, clicks=clicks, button=button)
        click_name = "double clicked" if clicks == 2 else f"{button} clicked"
        return f"{click_name.title()} at ({x}, {y})"

    def _move_mouse(self, x: int, y: int) -> str:
        import pyautogui

        pyautogui.moveTo(x, y, duration=0.15)
        return f"Moved mouse to ({x}, {y})"

    def _get_active_window_title(self) -> str:
        try:
            from tools.window_manager import WindowManager

            title = WindowManager.get_active_window_title()
            return title or "No active window title found."
        except Exception as exc:
            return f"Could not read active window: {exc}"

    def _list_windows(self) -> str:
        try:
            from tools.window_manager import WindowManager

            windows = WindowManager.get_all_windows()[:10]
            if not windows:
                return "No visible windows found."
            titles = [w["title"] for w in windows if w.get("title")]
            return "Open windows:\n" + "\n".join(f"- {title}" for title in titles[:10])
        except Exception as exc:
            return f"Could not list windows: {exc}"

    def _read_clipboard(self) -> str:
        try:
            import pyperclip

            text = pyperclip.paste() or ""
            if len(text) > 500:
                text = text[:500].rstrip() + "... truncated"
            return text or "Clipboard empty hai."
        except Exception as exc:
            return f"Clipboard read failed: {exc}"

    def _write_clipboard(self, text: str) -> str:
        try:
            import pyperclip

            pyperclip.copy(text)
            return "Clipboard cleared." if not text else "Clipboard updated."
        except Exception as exc:
            return f"Clipboard update failed: {exc}"

    def _get_automation(self):
        if self.automation is None:
            from tools.automation import AutomationTool

            self.automation = AutomationTool()
        return self.automation

    def _parse_keys(self, phrase: str) -> list[str]:
        phrase = phrase.lower().strip()
        phrase = phrase.replace(" plus ", "+")
        phrase = phrase.replace(" and ", "+")
        phrase = phrase.replace(" with ", "+")
        phrase = re.sub(r"\s+key\b", "", phrase)
        phrase = re.sub(r"\s+button\b", "", phrase)

        raw_parts = [part.strip() for part in re.split(r"\+|,", phrase) if part.strip()]
        if len(raw_parts) == 1:
            words = raw_parts[0].split()
            if len(words) > 1 and any(word in {"ctrl", "control", "alt", "shift", "win", "windows"} for word in words):
                raw_parts = words

        keys = []
        for part in raw_parts:
            part = part.strip()
            mapped = self.KEY_ALIASES.get(part, part)
            mapped = mapped.replace(" ", "")
            if mapped:
                keys.append(mapped)
        return keys

    def _extract_count(self, phrase: str) -> int:
        match = re.search(
            r"\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+times?$",
            phrase.lower().strip(),
        )
        if not match:
            return 1
        raw = match.group(1)
        if raw.isdigit():
            return max(1, min(int(raw), 20))
        return self.NUMBER_WORDS.get(raw, 1)

    def _target_to_url(self, target: str) -> str | None:
        low = target.lower()
        if low in self.WEBSITE_ALIASES:
            return self.WEBSITE_ALIASES[low]
        if low.startswith("http://") or low.startswith("https://"):
            return target
        if re.match(r"^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:/.*)?$", low):
            return "https://" + target
        return None

    def _target_to_path(self, target: str) -> Path | None:
        low = target.lower().strip()
        if low in {"project", "workspace", "current project", "pihu project"}:
            return self.workspace_dir

        if low in self.SPECIAL_FOLDERS:
            relative = self.SPECIAL_FOLDERS[low]
            return Path.home() / relative if relative else Path.home()

        expanded = Path(os.path.expandvars(os.path.expanduser(target)))
        if expanded.exists():
            return expanded.resolve()

        return None

    def _map_app(self, target: str) -> str:
        low = target.lower()
        return self.APP_ALIASES.get(low, low)

    def _sanitize_target(self, target: str) -> str:
        target = target.strip(" .,!?:;\"'")
        target = re.sub(r"^(?:the|my)\s+", "", target, flags=re.IGNORECASE)
        target = re.sub(
            r"\s+(?:app|application|program|please|pls|karo|kar do)$",
            "",
            target,
            flags=re.IGNORECASE,
        )
        return target.strip()

    def _clean(self, spoken_text: str) -> str:
        text = (spoken_text or "").strip()
        text = re.sub(r"^[,.\s]+|[,.\s]+$", "", text)
        text = re.sub(r"^(?:hey\s+)?pihu[:,\s]+", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"^(?:please|pls|zara|can you|could you|kya tum|tum)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        return text.strip()

    def _starts_with_literal_payload_command(self, cleaned: str) -> bool:
        return bool(
            re.match(
                r"^(?:type|write|likho|likh|enter text|run command|execute command|shell command)\b",
                cleaned,
                re.IGNORECASE,
            )
        )

    def _is_pending_active(self) -> bool:
        return (time.time() - self._pending_at) <= self.confirmation_ttl_s

    def _is_confirmation(self, cleaned: str) -> bool:
        return cleaned.lower().strip() in self.CONFIRM_WORDS

    def _is_cancel(self, cleaned: str) -> bool:
        return cleaned.lower().strip() in self.CANCEL_WORDS
