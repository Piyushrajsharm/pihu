"""
Pihu — Main Entrypoint
Initializes all modules and starts the main event loop.

Usage:
    python main.py              # Voice mode (microphone)
    python main.py --text       # Text mode (keyboard input)
"""

import sys
import argparse

# Add project root to path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from logger import get_logger

log = get_logger("MAIN")


def check_ollama():
    """Check if Ollama is running and accessible."""
    try:
        import ollama
        from config import OLLAMA_BASE_URL

        client = ollama.Client(host=OLLAMA_BASE_URL)
        models = client.list()
        model_names = [m.model for m in models.models] if hasattr(models, 'models') else []
        log.info("✅ Ollama connected | %d models available", len(model_names))

        for name in model_names:
            log.info("   📦 %s", name)

        return True

    except Exception as e:
        log.error("❌ Cannot connect to Ollama: %s", e)
        log.error("   Make sure Ollama is running: 'ollama serve'")
        return False


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
    
    # Silence technical logs in text mode for a cleaner UI
    if args.text:
        import logging
        logging.getLogger("pihu").setLevel(logging.WARNING)

    print_banner()

    # System info
    log.info("=" * 40)
    log.info("System startup check...")
    log.info("=" * 40)

    # Check Ollama
    if not check_ollama():
        log.warning("⚠️ Ollama not available — LLM features will be limited")
        log.warning("   Start Ollama with: ollama serve")
        log.warning("   Pull models with:")
        log.warning("     ollama pull qwen2.5:3b")
        log.warning("     ollama pull phi3:mini")
        log.warning("     ollama pull gemma3:4b")

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

    restart_count = 0
    max_rapid_restarts = 10
    rapid_restart_window_s = 60
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
                t for t in restart_timestamps if now - t < rapid_restart_window_s
            ]

            if len(restart_timestamps) >= max_rapid_restarts:
                log.critical(
                    "💀 %d crashes in %ds — entering cooldown (30s)",
                    max_rapid_restarts, rapid_restart_window_s,
                )
                traceback.print_exc()
                time.sleep(30)
                restart_timestamps.clear()
            else:
                log.error("💥 Crash #%d: %s", restart_count, e)
                traceback.print_exc()
                log.info("🔄 Auto-restarting in 3 seconds...")
                time.sleep(3)


if __name__ == "__main__":
    main_forever()
