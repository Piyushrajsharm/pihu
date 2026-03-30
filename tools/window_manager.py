"""
Pihu — Window Manager
Windows OS window management using pywin32.
Find, focus, wait-for, and manage application windows.
"""

import re
import time
import win32gui
import win32con
import win32process
from logger import get_logger

log = get_logger("WINMGR")


class WindowManager:
    """Manage OS windows — find, focus, wait, enumerate."""

    @staticmethod
    def get_all_windows() -> list[dict]:
        """Get all visible windows with title and handle."""
        windows = []

        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.strip():
                    windows.append({"hwnd": hwnd, "title": title})

        win32gui.EnumWindows(callback, None)
        return windows

    @staticmethod
    def find_window(title_pattern: str) -> int | None:
        """Find a window whose title matches the pattern (case-insensitive).

        Args:
            title_pattern: Substring or regex pattern to match window title

        Returns:
            Window handle (hwnd) or None
        """
        pattern = re.compile(title_pattern, re.IGNORECASE)
        result = None

        def callback(hwnd, _):
            nonlocal result
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if pattern.search(title):
                    result = hwnd
                    return False  # Stop enumeration

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            pass  # EnumWindows raises when callback returns False
        return result

    @staticmethod
    def focus_window(hwnd: int) -> bool:
        """Bring a window to the foreground and give it focus."""
        try:
            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # Bring to front
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            log.info("🪟 Focused window: %s", win32gui.GetWindowText(hwnd)[:60])
            return True
        except Exception as e:
            log.error("Failed to focus window: %s", e)
            return False

    @staticmethod
    def get_active_window_title() -> str:
        """Get the title of the currently focused window."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            return win32gui.GetWindowText(hwnd)
        except Exception:
            return ""

    @classmethod
    def wait_for_window(cls, title_pattern: str, timeout: float = 15.0) -> int | None:
        """Wait until a window matching the pattern appears.

        Args:
            title_pattern: Substring/regex to match
            timeout: Max seconds to wait

        Returns:
            Window handle or None if timeout
        """
        log.info("⏳ Waiting for window: '%s' (timeout=%ds)", title_pattern, timeout)
        t0 = time.time()
        while (time.time() - t0) < timeout:
            hwnd = cls.find_window(title_pattern)
            if hwnd:
                log.info("✅ Window found: %s (%.1fs)", win32gui.GetWindowText(hwnd)[:60], time.time() - t0)
                return hwnd
            time.sleep(0.5)
        log.warning("⏰ Timeout waiting for window: '%s'", title_pattern)
        return None

    @classmethod
    def focus_by_title(cls, title_pattern: str) -> bool:
        """Find a window by title and focus it."""
        hwnd = cls.find_window(title_pattern)
        if hwnd:
            return cls.focus_window(hwnd)
        log.warning("Window not found: '%s'", title_pattern)
        return False
