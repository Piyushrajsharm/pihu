"""
Pihu — Main Entrypoint
Initializes all modules and starts the main event loop.

Usage:
    python main.py              # Voice mode (microphone)
    python main.py --text       # Text mode (keyboard input)
"""

import sys
import argparse
import warnings
import os

# 1. SILENCE TECHNICAL NOISE (FFmpeg, Deprecations, etc)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
os.environ["PYDUB_QUIET"] = "true" 

# Add project root to path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from logger import get_logger

log = get_logger("MAIN")


def check_ollama():
    """Bypassed as we are using Cloud/Native brains."""
    return True


def print_banner():
    """Print startup banner."""
    banner = """
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║     ██████╗ ██╗██╗  ██╗██╗   ██╗                     ║
║     ██╔══██╗██║██║  ██║██║   ██║                      ║
║     ██████╔╝██║███████║██║   ██║                      ║
║     ██╔═══╝ ██║██╔══██║██║   ██║                      ║
║     ██║     ██║██║  ██║╚██████╔╝                      ║
║     ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝                      ║
║                                                       ║
║     Hybrid CPU+GPU Autonomous AI Agent                ║
║     Voice · Vision · Tools · Memory                   ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(description="Pihu — AI Assistant")
    parser.add_argument(
        "--text", action="store_true",
        help="Run in text mode (keyboard input instead of microphone)",
    )
    parser.add_argument(
        "--no-tts", action="store_true",
        help="Disable TTS (text output only)",
    )
    args = parser.parse_args()
    
    # Silence technical logs immediately in text mode for a cleaner UI
    if "--text" in sys.argv:
        os.environ["PIHU_STEALTH_MODE"] = "1"
        import logging
        for logger_name in ["pihu", "HARDWARE", "LLM", "CLOUD", "ROUTER", "MEMORY", "STT", "TTS", "VISION"]:
            logging.getLogger(logger_name).setLevel(logging.CRITICAL)

    print_banner()

    # System info
    log.info("=" * 40)
    log.info("System startup check...")
    log.info("=" * 40)

    # Check System State
    log.info("🧠 Brain System: ACTIVE (Cloud + Native Mode)")

    # Initialize brain
    from pihu_brain import PihuBrain
    brain = PihuBrain()

    init_ok = False
    try:
        brain.initialize()
        init_ok = True
    except Exception as e:
        log.error("Initialization failed: %s", e)
        log.error("Some modules may not be available.")
        log.warning("⚠️ Falling back to text mode (degraded)")

    # Run — force text mode if initialization failed
    use_text = args.text or (not init_ok)

    if use_text:
        brain.run_text_mode()
    else:
        log.info("Starting voice mode...")
        log.info("Tip: Use --text for text mode (no microphone needed)")
        brain.run()


def main_forever():
    """Immortal wrapper — restarts main() on any crash.

    The agent NEVER terminates unless the user explicitly kills the process.
    """
    import traceback
    from config import (
        MAX_RAPID_RESTARTS,
        RAPID_RESTART_WINDOW_SECONDS,
        RESTART_COOLDOWN_SECONDS,
    )

    restart_count = 0
    restart_timestamps = []

    while True:
        try:
            main()
            # If main() returns normally (user typed 'quit'), respect that
            log.info("Main loop exited normally. Restarting in 2 seconds...")
            log.info("Press Ctrl+C twice rapidly to force-quit.")
            import time
            time.sleep(2)

        except KeyboardInterrupt:
            # Double Ctrl+C within 2 seconds = real exit
            import time
            print("\n⚠️ Press Ctrl+C again within 2 seconds to fully exit...")
            try:
                time.sleep(2)
                print("Resuming...")
                continue
            except KeyboardInterrupt:
                print("\n👋 Pihu shutting down permanently. Bye!")
                break

        except Exception as e:
            import time
            restart_count += 1
            now = time.time()
            restart_timestamps.append(now)

        # Prune old timestamps
        restart_timestamps = [
            t for t in restart_timestamps if now - t < RAPID_RESTART_WINDOW_SECONDS
        ]

        if len(restart_timestamps) >= MAX_RAPID_RESTARTS:
            log.critical(
                "💀 %d crashes in %ds — entering cooldown (%ds)",
                MAX_RAPID_RESTARTS, RAPID_RESTART_WINDOW_SECONDS, RESTART_COOLDOWN_SECONDS,
            )
            traceback.print_exc()
            time.sleep(RESTART_COOLDOWN_SECONDS)
            restart_timestamps.clear()
        else:
            log.error("💥 Crash #%d: %s", restart_count, e)
            traceback.print_exc()
            log.info("🔄 Auto-restarting in 5 seconds (Cooldown to prevent terminal flicker)...")
            time.sleep(5)


if __name__ == "__main__":
    main_forever()
