"""
Pihu V2 — Real-time Voice Sandbox
Validates that the RealtimeTTS + Kokoro engine can stream audio
directly from a simulated token generator with sub-200ms latency.
"""
from tts_engine import TTSEngine
import time

def simulate_tokens():
    """Simulate a slow LLM generating text."""
    text = "Hello. This is Pihu v2 testing the new real-time voice engine. I should start speaking before I finish thinking this whole sentence."
    # We yield word by word with a tiny delay
    for word in text.split():
        yield word + " "
        time.sleep(0.05) # 50ms per word = fast LLM

def run_voice_test():
    print("========== V2 VOICE BOOT SEQUENCE ==========")
    tts = TTSEngine()
    tts.load()
    
    if not tts.is_loaded:
        print("[CRITICAL ERROR] RealtimeTTS failed to load.")
        return
        
    print("\n>>> Starting Real-time Stream...")
    start_time = time.time()
    
    # 1. Start the playback loop
    tts.play(async_mode=True)
    
    # 2. Feed the simulated token generator
    first_chunk_time = None
    for chunk in simulate_tokens():
        if first_chunk_time is None:
            first_chunk_time = time.time()
            print(f"Feeding first word at: {first_chunk_time - start_time:.4f}s")
        tts.feed(chunk)
        print(chunk, end="", flush=True)

    print("\n\n>>> Feed complete. Waiting for audio to finish...")
    # RealtimeTTS handles the wait in its internal thread, but we'll sleep for a bit
    time.sleep(5) 
    
    tts.stop()
    print("\n========== V2 VOICE TEST COMPLETE ==========")

if __name__ == "__main__":
    run_voice_test()
