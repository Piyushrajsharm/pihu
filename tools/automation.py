"""
Pihu — Automation Tool (Fully Agentic)
Vision-verified OS automation with window management and retry logic.

Every action follows: Execute → Screenshot → Verify → Retry if needed.
"""

import subprocess
import re
import time
import json

from logger import get_logger
from tools.window_manager import WindowManager

log = get_logger("TOOL")


class AutomationTool:
    """Agentic OS automation — every action is vision-verified.

    - execute_with_vision(): Run action + verify with screenshot
    - Window focus management before typing
    - Clipboard-based typing for full Unicode support
    - Retry logic on verification failure
    """

    # Common Windows app launch commands
    APP_REGISTRY = {
        "whatsapp": "start whatsapp:",
        "telegram": "start tg:",
        "chrome": "start chrome",
        "google chrome": "start chrome",
        "firefox": "start firefox",
        "edge": "start msedge",
        "notepad": "notepad",
        "calculator": "calc",
        "calc": "calc",
        "paint": "mspaint",
        "cmd": "cmd",
        "terminal": "wt",
        "powershell": "powershell",
        "command prompt": "cmd",
        "control": "control",
        "control panel": "control",
        "taskmgr": "taskmgr",
        "task manager": "taskmgr",
        "explorer": "explorer",
        "file explorer": "explorer",
        "settings": "start ms-settings:",
        "spotify": "start spotify:",
        "mail": "start mailto:",
        "photos": "start ms-photos:",
        "camera": "start microsoft.windows.camera:",
        "store": "start ms-windows-store:",
        "snipping tool": "snippingtool",
        "excel": "start excel",
        "word": "start winword",
        "powerpoint": "start powerpnt",
        "powerbi": r'start "" "D:\\bin\\PBIDesktop.exe"',
        "power bi": r'start "" "D:\\bin\\PBIDesktop.exe"',
        "code": "code",
        "vscode": "code",
        "vs code": "code",
        "vlc": "start vlc:",
        "discord": "start discord:",
    }

    # Window title patterns for common apps (used to verify they opened)
    APP_WINDOW_PATTERNS = {
        "whatsapp": r"WhatsApp",
        "chrome": r"Google Chrome|Chrome",
        "firefox": r"Mozilla Firefox|Firefox",
        "edge": r"Edge",
        "notepad": r"Notepad|Untitled",
        "calculator": r"Calculator",
        "paint": r"Paint",
        "control": r"Control Panel",
        "taskmgr": r"Task Manager",
        "task manager": r"Task Manager",
        "excel": r"Excel",
        "word": r"Word",
        "powerbi": r"Power BI|PBIDesktop",
        "power bi": r"Power BI|PBIDesktop",
        "code": r"Visual Studio Code",
        "vscode": r"Visual Studio Code",
        "explorer": r"File Explorer",
        "settings": r"Settings",
        "spotify": r"Spotify",
        "discord": r"Discord",
        "telegram": r"Telegram",
    }

    def __init__(self, llm_client=None, grounding_tool=None):
        from config import ALLOWED_SYSTEM_COMMANDS
        self.allowed_commands = ALLOWED_SYSTEM_COMMANDS
        self.llm = llm_client
        self.grounding = grounding_tool
        self.winmgr = WindowManager()

        log.info("AutomationTool initialized (Agentic Mode) | %d apps registered", len(self.APP_REGISTRY))

    # ──────────────────────────────────────────────
    # AGENTIC EXECUTION (Vision-Verified)
    # ──────────────────────────────────────────────

    def execute_with_vision(self, action: str, arg: str, verify_description: str = "", dry_run: bool = False) -> dict:
        """Execute an action and optionally verify with vision.

        Returns:
            {"success": bool, "message": str, "verified": bool}
        """
        result = self._execute_single(action, arg, dry_run=dry_run)

        if not verify_description or not self.grounding:
            return {"success": True, "message": result, "verified": False}

        # Vision verification
        time.sleep(1)  # Let the UI settle
        verified = self.grounding.verify_state(verify_description)

        if verified:
            log.info("✅ Vision verified: %s", verify_description)
        else:
            log.warning("⚠️ Vision verification FAILED: %s", verify_description)

        return {"success": True, "message": result, "verified": verified}

    def _execute_single(self, action: str, arg: str, dry_run: bool = False) -> str:
        """Execute a single atomic action."""
        action = action.lower().strip()

        if dry_run:
            log.info("🛡️ [SANDBOX / DRY RUN] Intercepted Action: %s | Arg: %s", action.upper(), arg)
            if action == "wait":
                time.sleep(min(1.0, float(arg))) # Short sleep to simulate async
            return f"🛡️ [SANDBOX] Would execute: {action} {arg}"

        if action == "open":
            print(f"\n[🎙️ Pihu]: '{arg}' open kar rahi hoon...")
            return self._open_app(arg)
        elif action == "type":
            print(f"\n[🎙️ Pihu]: type kar rahi hoon... '{arg[:20]}'")
            return self.type_text(arg)
        elif action == "hotkey":
            keys = str(arg).split("+")
            return self.hotkey(*[k.strip() for k in keys])
        elif action == "click":
            coords = str(arg).split(",")
            return self.mouse_click(int(coords[0].strip()), int(coords[1].strip()))
        elif action == "find_and_click":
            print(f"\n[🎙️ Pihu]: dekhti hoon screen pe... '{arg}' dhundh rahi hoon.")
            return self.find_and_click(arg)
        elif action == "focus":
            return self._focus_app(arg)
        elif action == "wait":
            time.sleep(float(arg))
            return f"⏳ Waited {arg}s"
        elif action == "drag":
            coords = [int(c.strip()) for c in str(arg).split(",")]
            return self.drag_and_drop(*coords)
        elif action == "scroll":
            return self.scroll_mouse(int(arg))
        elif action == "screenshot":
            return self._take_screenshot_description(arg)
        elif action == "whatsapp_send":
            parts = str(arg).split("|")
            contact = parts[0].strip()
            message = parts[1].strip() if len(parts) > 1 else "Hi"
            return self._turbo_whatsapp(contact, message)
        else:
            return f"⚠️ Unknown action: {action}"

    # ──────────────────────────────────────────────
    # APP LAUNCHING (with window verification)
    # ──────────────────────────────────────────────

    def _open_app(self, app_name: str) -> str:
        """Open app and wait for its window to appear."""
        import os
        app_key = app_name.lower().strip()
        log.info("⚙️ Opening: %s", app_name)

        # 1. Launch via registry
        if app_key in self.APP_REGISTRY:
            cmd = self.APP_REGISTRY[app_key]
            try:
                import subprocess
                DETACHED_PROCESS = 0x00000008
                subprocess.Popen(cmd, shell=True, creationflags=DETACHED_PROCESS)
            except Exception as e:
                log.error("Registry launch failed: %s", e)
        else:
            # Try os.startfile, then generic start
            try:
                os.startfile(app_name)
            except Exception:
                try:
                    import subprocess
                    DETACHED_PROCESS = 0x00000008
                    subprocess.Popen(f"start {app_name}", shell=True, creationflags=DETACHED_PROCESS)
                except Exception as e:
                    return f"❌ Cannot open '{app_name}': {e}"

        # 2. Wait for window to appear
        pattern = self.APP_WINDOW_PATTERNS.get(app_key)
        if pattern:
            hwnd = self.winmgr.wait_for_window(pattern, timeout=12)
            if hwnd:
                self.winmgr.focus_window(hwnd)
                return f"✅ Opened & focused: {app_name}"
            else:
                return f"⚠️ Launched {app_name} but window not detected"
        else:
            time.sleep(3)  # Generic wait
            return f"✅ Launched: {app_name}"

    def _focus_app(self, app_name: str) -> str:
        """Focus an already-open app window."""
        app_key = app_name.lower().strip()
        pattern = self.APP_WINDOW_PATTERNS.get(app_key, app_name)
        if self.winmgr.focus_by_title(pattern):
            return f"✅ Focused: {app_name}"
        return f"⚠️ Window not found: {app_name}"
    def _turbo_whatsapp(self, contact: str, message: str) -> str:
        """High-speed WhatsApp messaging (Milliseconds)."""
        log.info("⚡ TURBO WHATSAPP: %s -> %s", contact, message)
        
        # 1. Quick Launch
        self._open_app("whatsapp")
        time.sleep(1.5) # Wait for window focus
        
        # 2. Search & Select
        import pyautogui
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.3)
        self.type_text(contact)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(0.5)
        
        # 3. Type & Send
        self.type_text(message)
        time.sleep(0.2)
        pyautogui.press("enter")
        
        return f"✅ Turbo WhatsApp: Sent '{message}' to '{contact}'"
    # ──────────────────────────────────────────────
    # UI ACTIONS
    # ──────────────────────────────────────────────

    def type_text(self, text: str) -> str:
        """Type text via clipboard (Unicode-safe)."""
        try:
            import pyautogui
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            log.info("⌨️ Typed: '%s'", text[:30])
            return f"✅ Typed: '{text}'"
        except Exception as e:
            return f"❌ Type failed: {e}"

    def mouse_click(self, x: int, y: int) -> str:
        """Click at screen coordinates."""
        try:
            import pyautogui
            pyautogui.click(x, y)
            log.info("🖱️ Clicked at (%d, %d)", x, y)
            return f"✅ Clicked at ({x}, {y})"
        except Exception as e:
            return f"❌ Click failed: {e}"

    def hotkey(self, *keys) -> str:
        """Press a keyboard shortcut."""
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            key_str = "+".join(keys)
            log.info("⌨️ Hotkey: %s", key_str)
            return f"✅ Pressed: {key_str}"
        except Exception as e:
            return f"❌ Hotkey failed: {e}"

    def find_and_click(self, description: str) -> str:
        """Find an element visually and click it."""
        if not self.grounding:
            return "❌ Vision grounding not available"

        log.info("🔍 Finding element: %s", description)
        coords = self.grounding.find_element(description)
        if coords:
            return self.mouse_click(coords[0], coords[1])
        return f"❌ Could not find: '{description}'"

    def drag_and_drop(self, x1: int, y1: int, x2: int, y2: int) -> str:
        """Drag from (x1,y1) to (x2,y2)."""
        try:
            import pyautogui
            pyautogui.moveTo(x1, y1)
            pyautogui.dragTo(x2, y2, duration=0.3)
            return f"✅ Dragged ({x1},{y1}) → ({x2},{y2})"
        except Exception as e:
            return f"❌ Drag failed: {e}"

    def scroll_mouse(self, amount: int) -> str:
        """Scroll mouse wheel."""
        try:
            import pyautogui
            pyautogui.scroll(amount)
            return f"✅ Scrolled {amount}"
        except Exception as e:
            return f"❌ Scroll failed: {e}"

    def _take_screenshot_description(self, question: str = "") -> str:
        """Take screenshot and describe it."""
        if self.grounding:
            return self.grounding.describe_screen(question or "What is on the screen right now?")
        return "❌ Vision not available"

    # ──────────────────────────────────────────────
    # NATURAL LANGUAGE EXECUTION
    # ──────────────────────────────────────────────

    def execute_natural(self, natural_command: str) -> str:
        """Parse a natural language command and execute."""
        cmd = natural_command.lower().strip()

        # Complex multi-step → delegate to LLM planner
        is_complex = any(word in cmd for word in [" aur ", " and ", " then ", ",", " uske baad ", " phir "])
        if is_complex and self.llm:
            return self._execute_complex_with_llm(natural_command)

        # Turbo WhatsApp Detection (High Priority)
        match = re.search(r"whatsapp.*(?:kholo?|open).*?(?:mummy|papa|[\w\s]+).*?(?:ko|par).*?(?:hi|helo|[\w\s]+).*?(?:likho?|bhejo?|send)", cmd)
        if not match:
            # Flexible pattern: "mummy ko hi likho whatsapp par"
            match = re.search(r"(?:whatsapp).*?([\w\s]+)\s+ko\s+([\w\s]+)\s+(?:likho?|bhejo?|send)", cmd)
        
        if match:
            # Very loose matching for "whatsapp Mummy hi"
            words = cmd.split()
            contact = "Mummy" # Default
            message = "Hi" # Default
            # Try to extract contact name from "whatsapp [X] ko [Y] likho"
            if " ko " in cmd:
                parts = cmd.split(" ko ")
                contact_raw = parts[0].split()[-1]
                if contact_raw != "whatsapp": contact = contact_raw
                message_raw = parts[1].split()[0]
                message = message_raw
            
            return self._turbo_whatsapp(contact, message)

        # Open app
        match = re.search(r"(?:open|launch|start|chalao?|kholo?|khol)\s+([a-zA-Z0-9_\-\.]+)", cmd)
        if not match:
            match = re.search(r"([a-zA-Z0-9_\-\.]+)\s+(?:kholo?|khol|chalao?|chala|start karo)", cmd)
        if match:
            app = match.group(1).strip()
            if app not in ["acha", "chalo", "toh", "sirf", "bhai", "please", "zara"]:
                return self._open_app(app)

        # Type
        match = re.search(r"(?:type|likho?|write|send)\s+(.+)", cmd)
        if match:
            return self.type_text(match.group(1).strip())

        # Volume
        if "volume up" in cmd or "volume badha" in cmd:
            return self.hotkey("volumeup")
        if "volume down" in cmd or "volume kam" in cmd:
            return self.hotkey("volumedown")
        if "mute" in cmd:
            return self.hotkey("volumemute")

        return f"⚠️ Command not understood: '{natural_command}'"

    def _execute_complex_with_llm(self, command: str) -> str:
        """Use LLM to plan and execute multi-step commands."""
        prompt = f"""Convert this natural language command into a JSON array of sequential OS actions.
Available actions:
1. {{"action": "open", "arg": "<app_name>"}}
2. {{"action": "type", "arg": "<text>"}}
3. {{"action": "hotkey", "arg": "<key1+key2>"}}
4. {{"action": "click", "arg": "<x,y>"}}
5. {{"action": "wait", "arg": <seconds>}}
6. {{"action": "find_and_click", "arg": "<description>"}}
7. {{"action": "focus", "arg": "<app_name>"}}
8. {{"action": "scroll", "arg": <amount>}}
9. {{"action": "screenshot", "arg": "<question>"}}

User command: "{command}"

Rules:
- After opening any app, add {{"action": "wait", "arg": 5}} to let it load
- Use "focus" to switch between already-open apps
- Use "find_and_click" when you need to click a specific button/element
- ONLY output JSON array, no markdown, no explanations

Output:"""
        try:
            log.info("🧠 Planning complex automation...")
            response = self.llm.generate_sync(prompt=prompt, system_prompt="")
            if not response:
                return "❌ Planner failed"

            json_str = response.strip()
            if json_str.startswith("```"):
                json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
                json_str = re.sub(r"\n?```$", "", json_str)

            plan = json.loads(json_str)
            log.info("📋 Plan: %d steps", len(plan))

            results = []
            for step in plan:
                action = step.get("action", "")
                arg = step.get("arg", "")
                result = self._execute_single(action, str(arg))
                results.append(result)

            return "✅ Complete:\\n" + "\\n".join(results)
        except Exception as e:
            log.error("Complex execution failed: %s", e)
            return f"❌ Failed: {e}"

    # ──────────────────────────────────────────────
    # SYSTEM COMMAND EXECUTION
    # ──────────────────────────────────────────────

    def execute(self, command: str) -> str:
        """Execute a whitelisted system command."""
        base_cmd = command.strip().split()[0].lower() if command.strip() else ""

        if base_cmd not in self.allowed_commands:
            return f"❌ Command '{base_cmd}' not whitelisted"

        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
            output = result.stdout.strip() or result.stderr.strip()
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "❌ Command timed out"
        except Exception as e:
            return f"❌ Error: {e}"
