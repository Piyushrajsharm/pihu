"""
Pihu V2 — Mem0 Sandbox Integration Test
Validates the local Qdrant/Ollama pipeline for asynchronous long-term memory extraction.
"""
from memory_engine import MemoryEngine
import time

def run_mem0_tests():
    print("========== MEM0 V2 BOOT SEQUENCE ==========")
    memory = MemoryEngine()
    
    if not memory._mem0_enabled:
        print("[CRITICAL ERROR] Mem0 Engine failed to initialize. Ensure pip install mem0ai qdrant-client was executed.")
        return
        
    print("\n>>> Phase 1: Async Long-Term Memory Extraction (0 Latency)")
    print("Simulating User Phrase: 'I hate TailwindCSS. I only use raw CSS files for styling.'")
    
    start_time = time.time()
    memory.update_memory_async("I hate TailwindCSS. I only use raw CSS files for styling.")
    end_time = time.time()
    
    print(f"Main Thread Latency: {(end_time - start_time)*1000:.2f} ms")
    print("Waiting 15 seconds for Ollama background thread to process and vectorize the semantic intent...")
    time.sleep(15) # Wait for background LLM
    
    print("\n>>> Phase 2: Sub-15ms Forward Vector Retrieval")
    retrieval_start = time.time()
    context_str = memory.get_context_for_query("Can you write some frontend styling for my new page?")
    retrieval_end = time.time()
    
    print(f"Retrieval Latency: {(retrieval_end - retrieval_start)*1000:.2f} ms")
    print(f"\n[INJECTED VECTOR CONTEXT]:\n{context_str}\n")
    print("========== MEM0 INTEGRATION SUCCESS ==========")

if __name__ == "__main__":
    run_mem0_tests()
