import sys
import logging
from logger import get_logger

# We need to initialize the actual dependencies
from llm.cloud_llm import CloudLLM
from intent_classifier import IntentClassifier
from tools.composio_bridge import ComposioBridge
from graph_router import GraphRouter

log = get_logger("TEST")

def test_phase_1():
    print("\n--- PHASE 1: LANGGRAPH & COMPOSIO TEST ---")
    
    # 1. Initialize dependencies
    cloud_llm = CloudLLM()
    health = cloud_llm.health_check()
    if not health.get("available"):
        print("❌ CloudLLM failed. Is NVIDIA_NIM_API_KEY set in .env?")
        return
    print("✅ CloudLLM initialized.")
    
    composio = ComposioBridge(cloud_llm=cloud_llm)
    if not composio.is_available:
        print("❌ ComposioBridge failed to initialize.")
        return
    print("✅ ComposioBridge initialized.")
    
    intent_classifier = IntentClassifier()
    
    # 2. Build GraphRouter
    tools_dict = {"composio": composio}
    router = GraphRouter(
        local_llm=cloud_llm, # Fallback to cloud for the test
        cloud_llm=cloud_llm,
        intent_classifier=intent_classifier,
        memory=None, # Skip memory for isolated test
        tools_dict=tools_dict
    )
    
    if not router.is_available:
        print("❌ GraphRouter failed to initialize.")
        return
    print("✅ GraphRouter compiled.\n")
    
    # 3. Test Execution
    # We ask a question that triggers Composio via the keyword "GitHub"
    test_query = "What is trending on GitHub right now? Give me a short summary."
    print(f"User Input: '{test_query}'")
    
    print("Executing Graph...")
    result = router.execute(test_query)
    
    print("\n--- TEST RESULTS ---")
    print(f"Detected Intent: {result.get('intent')}")
    print(f"Pipeline Selected: {result.get('pipeline')}")
    print(f"Final LLM Response:\n{result.get('final_response')}")

if __name__ == "__main__":
    test_phase_1()
