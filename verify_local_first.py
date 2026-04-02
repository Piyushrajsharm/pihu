from pihu_brain import PihuBrain
import sys

def verify_no_ollama_mode():
    print("🧠 Initializing PihuBrain (NATIVE Direct Loading Verification)...")
    try:
        brain = PihuBrain()
        # Mocking sub-system loads to avoid hardware delays
        brain.initialize()
        
        print("\n✅ PihuBrain initialized successfully.")
        print(f"📡 Router Primary: {brain.router.local_llm.llm is not None}")
        print(f"📡 Native Model Loaded: {brain.router.local_llm.is_available}")
        
        # Test routing logic
        from intent_classifier import Intent
        chat_intent = Intent(type="chat", confidence=0.9, raw_input="Hi Pihu!")
        
        route_chat = brain.router.route(chat_intent)
        
        print("\n🧪 Routing Test:")
        print(f"  - Message: 'Hi Pihu!' -> Pipeline: {route_chat.pipeline}")
        
        if route_chat.pipeline == "local_llm":
            print("\n🎉 SUCCESS: Pihu is now running WITHOUT Ollama!")
        else:
            print("\n❌ FAILURE: Routing logic check failed.")
            
    except Exception as e:
        print(f"\n❌ ERROR during initialization: {e}")

if __name__ == "__main__":
    verify_no_ollama_mode()
