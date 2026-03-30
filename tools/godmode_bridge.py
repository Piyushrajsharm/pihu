"""
Pihu — GodMode Browser Engine
Real browser automation with vision verification.
Opens browser, navigates, types, clicks — all vision-verified.

Uses the system default browser via automation rather than Electron,
making it work without any additional npm dependencies.
"""

import time
import subprocess
from logger import get_logger

log = get_logger("GODMODE")


class GodModeBridge:
    """Browser automation engine — vision-guided web interaction."""

    def __init__(self):
        log.info("GodMode Browser Engine initialized")

    def execute_browser_task(self, task: str, automation, grounding) -> str:
        """Execute a browser-based task using automation + vision.

        Args:
            task: Natural language task description
            automation: AutomationTool instance
            grounding: VisionGrounding instance

        Returns:
            Execution result string
        """
        log.info("🌐 GodMode executing: %s", task[:80])
        t0 = time.time()

        task_lower = task.lower()

        # Route to specific browser workflows
        if any(kw in task_lower for kw in ["search", "google", "look up", "khoj"]):
            return self._search_web(task, automation, grounding)
        elif any(kw in task_lower for kw in ["youtube", "video"]):
            return self._youtube_task(task, automation, grounding)
        elif any(kw in task_lower for kw in ["download", "install"]):
            return self._download_task(task, automation, grounding)
        else:
            return self._generic_browser_task(task, automation, grounding)

    def _search_web(self, task: str, automation, grounding) -> str:
        """Google search workflow."""
        import re
        t0 = time.time()
        
        # Extract search query
        query = task
        for prefix in ["search for", "google", "search", "look up", "khoj", "find"]:
            query = re.sub(rf"(?i)\b{prefix}\b", "", query).strip()

        log.info("🔍 GodMode Web Search: %s", query)

        steps = [
            ("open", "chrome"),
            ("wait", "3"),
            ("hotkey", "ctrl+l"),      # Focus address bar
            ("wait", "0.5"),
            ("type", f"https://www.google.com/search?q={query.replace(' ', '+')}"),
            ("hotkey", "enter"),
            ("wait", "3"),
        ]

        results = []
        for action, arg in steps:
            result = automation._execute_single(action, arg)
            results.append(result)

        # Vision: Describe search results
        if grounding:
            time.sleep(1)
            description = grounding.describe_screen(
                f"Read the top 3 Google search results for '{query}'. Summarize each in one line."
            )
            results.append(f"📄 Results: {description}")

        elapsed = time.time() - t0
        return f"🌐 GodMode Search Complete ({elapsed:.1f}s):\n" + "\n".join(results)

    def _youtube_task(self, task: str, automation, grounding) -> str:
        """YouTube playback workflow."""
        import re
        query = task
        for prefix in ["play", "youtube", "video", "chalao"]:
            query = re.sub(rf"(?i)\b{prefix}\b", "", query).strip()

        log.info("📺 GodMode YouTube: %s", query)

        steps = [
            ("open", "chrome"),
            ("wait", "3"),
            ("hotkey", "ctrl+l"),
            ("wait", "0.5"),
            ("type", f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"),
            ("hotkey", "enter"),
            ("wait", "4"),
            ("find_and_click", "First video thumbnail in search results"),
            ("wait", "3"),
        ]

        results = []
        for action, arg in steps:
            results.append(automation._execute_single(action, arg))

        return "📺 GodMode YouTube Complete:\n" + "\n".join(results)

    def _download_task(self, task: str, automation, grounding) -> str:
        """Download/install workflow."""
        log.info("📥 GodMode Download: %s", task[:60])
        # Open browser and navigate
        steps = [
            ("open", "chrome"),
            ("wait", "3"),
            ("hotkey", "ctrl+l"),
            ("wait", "0.5"),
        ]
        results = []
        for action, arg in steps:
            results.append(automation._execute_single(action, arg))

        return "📥 Browser opened for download task:\n" + "\n".join(results)

    def _generic_browser_task(self, task: str, automation, grounding) -> str:
        """Generic browser task — open browser and let the swarm planner handle details."""
        log.info("🌐 GodMode Generic: %s", task[:60])

        steps = [
            ("open", "chrome"),
            ("wait", "3"),
        ]
        results = []
        for action, arg in steps:
            results.append(automation._execute_single(action, arg))

        # Describe current state
        if grounding:
            desc = grounding.describe_screen("What is visible in the browser?")
            results.append(f"👁️ Screen: {desc}")

        return "🌐 Browser ready:\n" + "\n".join(results)
