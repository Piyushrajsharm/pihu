import sys
import logging
import asyncio

# Set up logging to stdout for the test
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from config import LANGGRAPH_ENABLED
from graph_router import GraphRouter
from intent_classifier import IntentClassifier

class MockLLM:
    def __init__(self, name):
        self.name = name
        self.is_available = True
    
    def generate_batch(self, prompt, context=None):
        return f"[{self.name}] Final generated response based on: '{prompt}' and {len(context) if context else 0} context items."

class MockMemory:
    def retrieve(self, text):
        return ["Memory Context 1", "Memory Context 2"]

class MockTool:
    def __init__(self, name):
        self.name = name
        self.is_available = True
        
    def execute(self, prompt):
        # Return a generator like Composio does
        yield f"[{self.name}] Tool executed successfully for '{prompt}'."

def main():
    print("=== Testing LangGraph Router ===")
    
    intent_classifier = IntentClassifier()
    memory = MockMemory()
    local_llm = MockLLM("Local_Llama")
    cloud_llm = MockLLM("Cloud_NVIDIA")
    
    tools = {
        "composio": MockTool("ComposioBridge"),
        "vision": MockTool("VisionTool")
    }
    
    router = GraphRouter(
        local_llm=local_llm,
        cloud_llm=cloud_llm,
        intent_classifier=intent_classifier,
        memory=memory,
        tools_dict=tools
    )
    
    if not router.is_available:
        print("LangGraph is not available. Ensure dependencies are installed.")
        return
        
    print("\n--- Test 1: Standard Chat ---")
    res1 = router.execute("Hello Pihu, how are you today?")
    print(f"Result State: {res1['intent']} -> {res1['pipeline']} -> {res1['final_response']}")
    
    print("\n--- Test 2: Tool Routing (Composio) ---")
    res2 = router.execute("Check my GitHub notifications and summarize them.")
    print(f"Result State: {res2['intent']} -> {res2['pipeline']}")
    print(f"Tool Results: {res2['tool_results']}")
    print(f"Final Output: {res2['final_response']}")

if __name__ == "__main__":
    main()
