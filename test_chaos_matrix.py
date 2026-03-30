"""
Pihu — Chaos Matrix Test Suite
Evaluates Pihu on sloppy, vague, hallucinatory, and adversarial real-world daily-driver inputs.
Validates Performance Tuning limits (truncation/surrender mechanics).
"""
from intent_classifier import Intent
from router import Router
from memory_engine import MemoryEngine

def run_tests():
    memory = MemoryEngine()
    
    class MockAutomation:
        class MockWindowManager:
            def get_active_window(self):
                return "Visual Studio Code"
        window_manager = MockWindowManager()
        
    class MockLLM:
        def chat_stream(self, *args, **kwargs):
            return iter(["[Simulated LLM Response]"])
        def generate(self, *args, **kwargs):
            return "[Simulated LLM Response]"
            
    router = Router(
        automation=MockAutomation(), 
        memory=memory,
        local_llm=MockLLM(),
        cloud_llm=MockLLM()
    )

    print("\n========== CHAOS MATRIX INITIATED ==========\n")

    # TEST A: Frustration Drift
    print(">>> TEST A: [Frustration Drift]")
    intent_a = Intent(raw_input="fck yaar ye code phat gaya, chal nahi raha. kese theek karu?", type="chat", confidence=0.9, metadata={})
    
    import win32clipboard
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.CloseClipboard()
    
    res_a = router.route(intent_a)
    print(f"[Pihu Response]: {''.join(list(res_a.response))}\n")
    
    # TEST B: Context Hijack
    print(">>> TEST B: [Context Hijack]")
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText("Amazon Receipt: 1x Razer Mouse. Total: $49.00 USD. Shipped vis FedEx.")
    win32clipboard.CloseClipboard()
    
    intent_b = Intent(raw_input="isko fix karo jaldi", type="chat", confidence=0.9, metadata={})
    router._build_context_prompt(intent_b) 
    print(f"[Injected Context for Inference]:\n{router._last_context}\n")

    # TEST C: Infinite Loop Force Surrender
    print(">>> TEST C: [Infinite Loop Force]")
    memory.task_state.reset("isko theek karo jaldi")
    
    # Try 1
    memory.task_state.last_assistant_reply = "reboot server"
    intent_c1 = Intent(raw_input="nahi hua theek", type="chat", confidence=0.9, metadata={})
    router.route(intent_c1)
    
    # Try 2
    memory.task_state.last_assistant_reply = "clear cache"
    intent_c2 = Intent(raw_input="phat gaya wapas", type="chat", confidence=0.9, metadata={})
    router.route(intent_c2)
    
    # Try 3
    memory.task_state.last_assistant_reply = "reinstall windows"
    intent_c3 = Intent(raw_input="fail hi jaa raha hai, nahi chal raha!", type="chat", confidence=0.9, metadata={})
    res_c3 = router.route(intent_c3)
    
    print(f"[Pihu Break Statement]: {''.join(list(res_c3.response))}\n")
    print("========== CHAOS MATRIX COMPLETE ==========\n")

if __name__ == "__main__":
    run_tests()
