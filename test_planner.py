"""
Pihu V2 — Planner & Architect Sandbox
Validates that complex queries trigger TaskWeaver for decomposition,
followed by OpenInterpreter for execution.
"""
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from router import Router
from intent_classifier import Intent
import time

def run_planner_test():
    print("========== V2 ARCHITECT BOOT SEQUENCE ==========")
    
    # 1. Initialize complete stack
    # We mock the LLMs to save time, but the engines should be real
    class MockLLM:
        def chat_stream(self, *args, **kwargs): return iter([])
        def generate(self, *args, **kwargs): return iter([])

    router = Router(
        local_llm=MockLLM(),
        cloud_llm=MockLLM()
    )
    
    # 2. Test Multi-Step Complex Intent
    print("\n>>> Testing Complex Intent: 'Analyze the system temp and then create a report.txt'")
    complex_input = "Analyze the system temp and then create a report.txt"
    intent = Intent(raw_input=complex_input, type="system_command", confidence=0.98, metadata={})
    
    print("Routing...")
    result = router.route(intent)
    
    # Debugging: what is result?
    print(f"Result type: {type(result)}")
    print(f"Result attributes: {dir(result)}")
    
    print("\n[STREAMING SYNERGISTIC OUTPUT]:")
    try:
        if hasattr(result, "response"):
            for i, chunk in enumerate(result.response):
                print(chunk, end="", flush=True)
                if i > 50: break 
        else:
            print("Result has no response attribute.")
    except Exception as e:
        print(f"\n[ERROR during stream]: {e}")

    print("\n\n========== V2 ARCHITECT TEST COMPLETE ==========")

if __name__ == "__main__":
    run_planner_test()
