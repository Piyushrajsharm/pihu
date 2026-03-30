"""
Pihu V2 — RAG Context Sandbox
Validates that LlamaIndex correctly isolates the "needle in the haystack"
from a noisy OCR screen dump.
"""
from context_rag_engine import ContextRAGEngine
import time

def run_rag_test():
    print("========== V2 COGNITIVE FILTER BOOT SEQUENCE ==========")
    rag = ContextRAGEngine()
    
    if not rag.is_available:
        print("[CRITICAL ERROR] LlamaIndex Engine failed to load.")
        return
        
    # 1. Create a "Noisy Haystack"
    # A mix of irrelevant system logs and one hidden "Secret Key"
    noisy_context = """
    [SYSTEM LOG 08:00:01] Initialization start.
    [SYSTEM LOG 08:00:05] Checking disk space... 80% free.
    [SYSTEM LOG 08:00:10] Network interface eth0 up.
    [USER DATA] The secret code for the vault is: 'PIHU_RAG_SUCCESS'.
    [SYSTEM LOG 08:00:15] RAM usage: 4.2GB / 16GB.
    [SYSTEM LOG 08:00:20] Kernel version 6.5.0-x86_64.
    [SYSTEM LOG 08:00:25] Thermal state: 45C - Optimal.
    [SYSTEM LOG 08:00:30] Battery at 100%. Charged.
    [SYSTEM LOG 08:00:35] Background process 'docker' active.
    """
    
    # 2. Query for the "Needle"
    user_query = "What is the secret vault code?"
    
    print(f"\nUser Query: '{user_query}'")
    print(f"Raw Context Size: {len(noisy_context)} characters")
    
    start_time = time.time()
    filtered_context = rag.filter_context(user_query, noisy_context, top_k=1)
    end_time = time.time()
    
    print(f"\nFiltered Context:\n{filtered_context}")
    print(f"\nFiltering Latency: {(end_time - start_time)*1000:.2f}ms")
    
    # Check if the needle was found and the noise was removed
    success = "PIHU_RAG_SUCCESS" in filtered_context and "Kernel version" not in filtered_context
    
    print(f"Semantic Extraction Success: {'✅ YES' if success else '❌ NO'}")
    print("========== V2 COGNITIVE FILTER TEST COMPLETE ==========")

if __name__ == "__main__":
    run_rag_test()
