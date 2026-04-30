
import sys
import time
import logging

# Reconfigure stdout for Windows terminal compatibility
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pihu_brain import PihuBrain
from logger import get_logger

log = get_logger("TEST-CHAT")

def test_chat():
    print("="*50)
    print("🚀 STARTING END-TO-END CHAT VERIFICATION")
    print("="*50)
    
    # Initialize Brain in backend mode (fastest for test)
    brain = PihuBrain(backend_mode=True)
    brain.initialize()
    
    if not brain.router:
        print("❌ Router failed to initialize")
        return

    user_input = "Hi Pihu, kaise ho? Aaj ka plan kya hai?"
    print(f"\nUSER: {user_input}")
    print("PIHU (Streaming): ", end="", flush=True)
    
    # 1. Pipeline Routing
    from intent_classifier import Intent
    intent = brain.intent_classifier.classify(user_input)
    result = brain.router.route(intent)
    
    # 2. Response Generation
    response_text = ""
    for chunk in result.response:
        print(chunk, end="", flush=True)
        response_text += chunk
        
    print("\n" + "="*50)
    if response_text:
        print("✅ SUCCESS: Pihu generated a response.")
        # Persona check: basic keywords
        hindi_keywords = ["hai", "hoon", "nahi", "kya", "babu", "yaar", "theek"]
        if any(w in response_text.lower() for w in hindi_keywords):
            print("✅ PERSONA VERIFIED: Hinglish detected.")
        else:
            print("⚠️ PERSONA WARNING: No common Hinglish keywords detected.")
    else:
        print("❌ FAILURE: No response generated.")
    
    print("="*50)

if __name__ == "__main__":
    test_chat()
