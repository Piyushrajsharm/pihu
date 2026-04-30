"""
Pihu — Quick Chat Shortcut
Simple entrypoint for text-based terminal conversation.
"""

import sys
import subprocess
from pathlib import Path

def start_chat():
    main_py = Path(__file__).parent / "main.py"
    
    print("🚀 Pihu Terminal Chat starting...")
    try:
        # We use subprocess to run the main menu with the correct flags
        subprocess.run([sys.executable, str(main_py), "--text"], check=True)
    except KeyboardInterrupt:
        print("\n👋 Pihu: Bye bye! Phir milenge! ❤️")
    except Exception as e:
        print(f"❌ Error starting chat: {e}")

if __name__ == "__main__":
    start_chat()
