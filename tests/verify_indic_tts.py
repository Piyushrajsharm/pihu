import sys
import os
import time

# Ensure pihu root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tts_engine import TTSEngine
from logger import get_logger

log = get_logger("TEST-TTS")

def test_synthesis():
    print("[*] Initializing Indic-TTS Engine...")
    engine = TTSEngine()
    
    # Load models
    engine.load()
    
    if not engine.is_loaded:
        print("[!] Failed to load TTS engine. Check if models exist in data/tts_models/hi")
        return

    test_text = "Piyush, maine Indic-TTS setup kar diya hai. Ab main natural bol sakti hoon. ❤️"
    print(f"[*] Synthesizing: {test_text}")
    
    t0 = time.time()
    try:
        # We'll use synthesize() which should play it
        # Since we are in a headless/terminal env, sounddevice might fail if no audio device
        # but the synthesis part should still work.
        engine.synthesize(test_text)
        print(f"[+] Multi-sentence synthesis completed in {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"[!] Synthesis/Playback failed: {e}")

if __name__ == "__main__":
    test_synthesis()
