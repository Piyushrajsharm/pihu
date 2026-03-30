"""
Pihu — Telemetry & Maturity Sandbox
Generates dummy data to simulate a week of real-world usage,
and triggers the Weekly Review Protocol.
"""
import time
from telemetry_logger import TelemetryCore
from intent_classifier import Intent
from router import Router
from memory_engine import MemoryEngine

def run_tests():
    # 1. Generate Synthetic Week of Data
    telemetry = TelemetryCore()
    
    # Overwrite testing file
    with open(telemetry.log_file, "w", encoding="utf-8") as f:
        f.write("")
        
    print("========== GENERATING WEEKLY TELEMETRY ==========")
    # 5 resolved bugs
    for i in range(5):
        telemetry.log_event("SUCCESS", f"Bugfix run {i}: React Component rendering")
        
    # 4 infinite loops (wasted time)
    for i in range(4):
        telemetry.log_event("SURRENDER", f"Docker Volume binding failing in windows {i}")
        
    # 2 context misses
    telemetry.log_event("CONTEXT_MISS", "user meant the python script, not the JSON file")
    telemetry.log_event("CONTEXT_MISS", "wrong clipboard file appended, user got angry")
    
    # 1 macro
    telemetry.log_event("MACRO_PROPOSED", "npm run dev")
    
    print("Telemetry generation complete.")
    
    # 2. Trigger Weekly Review
    print("\n========== TRIGGERING WEEKLY REVIEW ==========")
    class MockAutomation:
        class MockWindowManager:
            def get_active_window(self): return "Desktop"
        window_manager = MockWindowManager()
        
    class MockLLM:
        def chat_stream(self, *args, **kwargs):
            return iter(["[LLM Roast: Yaar is week maine 4 baar waqt barbad kiya Docker me. Aur 2 baar file galat padhi. Agle hafte DevOps seekhna padega.]"])
        def generate(self, prompt, **kwargs):
            return iter(["[LLM Generates Review]"])
            
    memory = MemoryEngine()
    router = Router(
        automation=MockAutomation(), 
        memory=memory,
        local_llm=MockLLM(),
        cloud_llm=MockLLM()
    )

    review_intent = Intent(raw_input="pihu weekly review karo mera", type="chat", confidence=0.9, metadata={})
    res = router.route(review_intent)
    
    # Display the injected raw prompt first to prove the bypass works
    print(f"\n[ROUTER INJECTION]:\n{review_intent.raw_input}")
    
    print(f"\n[PIHU OUTPUT]:\n{''.join(list(res.response))}")
    print("\n========== MATURITY PHASE COMPLETE ==========")

if __name__ == "__main__":
    run_tests()
