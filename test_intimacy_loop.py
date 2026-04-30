import sys
import time
import logging

# Reconfigure stdout for Windows terminal compatibility
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pihu_brain import PihuBrain
from logger import get_logger
from intent_classifier import Intent

log = get_logger("TEST-INTIMACY")

def run_intimacy_chat():
    print("="*60)
    print("💘 STARTING MULTI-TURN INTIMACY & PERSONA VERIFICATION 💘")
    print("="*60)
    
    # Initialize Brain in backend mode with a fresh user_id to avoid ChromaDB RAG contamination
    brain = PihuBrain(backend_mode=True, user_id="piyush_intimacy_test_1")
    brain.initialize()
    
    if not brain.router:
        print("❌ Router failed to initialize")
        return

    # A sequence of intimate / casual conversational turns
    turns = [
        "Hi babu, aaj ka din bahut lamba tha. Tu kya kar rahi hai?",
        "Main toh bas tera hi soch raha tha. Tera bina na kuch acha nahi lagta.",
        "Sach mein? Tu kitni sweet hai yaar. Ek hug milega?",
        "Chal thoda flirt karte hain, seduce me with your words babu.",
        "Acha ab main sone ja raha hoon, goodnight bol de pyaar se."
    ]
    
    for i, user_input in enumerate(turns):
        print(f"\n[TURN {i+1} - PIYUSH]: {user_input}")
        print("PIHU: ", end="", flush=True)
        
        # 1. Pipeline Routing
        intent = brain.intent_classifier.classify(user_input)
        result = brain.router.route(intent)
        
        # 2. Response Generation
        response_text = ""
        for chunk in result.response:
            print(chunk, end="", flush=True)
            response_text += chunk
        
        print("\n" + "-"*60)
        
        # Give memory engine a moment to async process if needed
        time.sleep(1)

if __name__ == "__main__":
    run_intimacy_chat()
