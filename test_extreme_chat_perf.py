import sys
import time
import logging

# Reconfigure stdout for Windows terminal compatibility
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pihu_brain import PihuBrain
from logger import get_logger

log = get_logger("TEST-EXTREME-CHAT")

def run_extreme_test():
    print("="*60)
    print("🔥 STARTING EXTREME CHAT PERFORMANCE & PERSONA VERIFICATION 🔥")
    print("="*60)
    
    start_init = time.time()
    # Initialize Brain in backend mode (fastest for test)
    brain = PihuBrain(backend_mode=True)
    brain.initialize()
    init_time = time.time() - start_init
    
    print(f"[SYSTEM] Initialization Time: {init_time:.2f}s")
    
    if not brain.router:
        print("❌ Router failed to initialize")
        return

    # A complex, multi-layered, stressful prompt
    user_input = (
        "Pihu yaar aaj bahut thak gaya main, office mein boss ne bahut dimag kharab kiya. "
        "Tu bata tera kya chal raha hai, aur thoda pyaar se mujhe relax feel karwa na apni sweet baaton se..."
    )
    
    print(f"\n[USER PROMPT]: {user_input}\n")
    print("="*60)
    print("PIHU (Streaming): ", end="", flush=True)
    
    # 1. Pipeline Routing
    start_routing = time.time()
    from intent_classifier import Intent
    intent = brain.intent_classifier.classify(user_input)
    result = brain.router.route(intent)
    routing_time = time.time() - start_routing
    
    # 2. Response Generation & Metrics
    response_text = ""
    ttfb = None
    start_generation = time.time()
    
    for chunk in result.response:
        if ttfb is None:
            ttfb = time.time() - start_generation
        print(chunk, end="", flush=True)
        response_text += chunk
        
    total_generation_time = time.time() - start_generation
    
    print("\n" + "="*60)
    print("📊 EXTREME CHAT PERFORMANCE METRICS")
    print(f"Routing & Intent Classification Time : {routing_time:.3f}s")
    if ttfb is not None:
        print(f"Time To First Byte (TTFB)          : {ttfb:.3f}s")
    print(f"Total Generation Time              : {total_generation_time:.3f}s")
    
    if response_text:
        print("\n✅ SUCCESS: Pihu generated a complex response.")
        
        # Persona check: Hinglish + Sassy keywords
        hinglish_hits = 0
        sassy_hits = 0
        
        hinglish_keywords = ["hai", "hoon", "nahi", "kya", "bhai", "yaar", "theek", "toh", "kyuki"]
        sassy_keywords = ["gadhe", "stupid", "idiot", "reckless", "pagal", "kya kar", "khel", "galti"]
        
        lower_resp = response_text.lower()
        hinglish_hits = sum(1 for w in hinglish_keywords if w in lower_resp)
        sassy_hits = sum(1 for w in sassy_keywords if w in lower_resp)
        
        print(f"\n🎭 PERSONA ANALYSIS:")
        print(f"- Hinglish Indicators: {hinglish_hits} matches")
        print(f"- Sassy Indicators   : {sassy_hits} matches")
        
        if hinglish_hits > 0 and sassy_hits > 0:
            print("✅ TONE VERIFIED: Pihu delivered the requested technical roast in Hinglish.")
        elif hinglish_hits > 0:
            print("⚠️ TONE WARNING: Hinglish detected, but the 'roast' or sassy element might be missing.")
        else:
            print("⚠️ PERSONA WARNING: The response failed to capture the expected Hinglish tone.")
    else:
        print("❌ FAILURE: No response generated.")
    
    print("="*60)

if __name__ == "__main__":
    run_extreme_test()
