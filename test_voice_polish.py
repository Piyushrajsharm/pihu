"""
Pihu — Voice Test
Validates that the configured TTS backend can synthesize clear
Hindi/Hinglish-style companion speech.
"""
from tts_engine import TTSEngine
import time


def simulate_tokens():
    """Simulate a slow LLM generating Hinglish text."""
    text = "Hi Piyush. Main Pihu hoon, tumhari sweet si girlfriend. Bolo, aaj kya karna hai?"
    for word in text.split():
        yield word + " "
        time.sleep(0.05)  # 50ms per word


def run_voice_test():
    print("=" * 50)
    print("  Pihu — Voice Test")
    print("=" * 50)

    tts = TTSEngine()
    tts.load()

    if not tts.is_loaded:
        print("[CRITICAL ERROR] TTS failed to load.")
        print("On Windows, check SAPI voices. For Indic-TTS, run `python scripts/setup_indic_tts.py`.")
        return

    print(f">>> Loaded TTS backend: {tts.backend}")

    # --- Test 1: feed/play API (simulated streaming) ---
    print("\n>>> Test 1: Streaming feed/play API")
    start_time = time.time()

    for chunk in simulate_tokens():
        tts.feed(chunk)
        print(chunk, end="", flush=True)

    print("\n\n>>> Feed complete. Playing synthesized audio...")
    tts.play(async_mode=False)  # Synchronous so we hear it

    elapsed = time.time() - start_time
    print(f">>> Test 1 done in {elapsed:.1f}s")

    time.sleep(0.5)

    # --- Test 2: one-shot synthesize ---
    print("\n>>> Test 2: One-shot synthesize()")
    t0 = time.time()
    tts.synthesize("Pihu ready hai. Bolo jaan, kya karna hai?")
    print(f">>> Test 2 done in {time.time() - t0:.1f}s")

    tts.stop()
    print("\n" + "=" * 50)
    print("  Voice Test Complete")
    print("=" * 50)


if __name__ == "__main__":
    run_voice_test()
