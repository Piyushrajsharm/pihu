from llm.llama_cpp_llm import LlamaCppLLM
import time

def test_native_llm():
    print("Testing Native LlamaCppLLM (Phi-3.5-mini)...")
    llm = LlamaCppLLM()
    
    if not llm.is_available:
        print("❌ Model not available. Check paths in config.py.")
        return

    print("🧠 Generating test response...")
    start = time.time()
    response = llm.generate("Hi Pihu, say 'READY' if you are working.", stream=False)
    elapsed = time.time() - start
    
    print(f"\n🤖 Pihu: {response}")
    print(f"⏱️ Time taken: {elapsed:.2f}s")
    
    if "READY" in response.upper():
        print("\n✅ Native LLM is WORKING PERFECTLY!")
    else:
        print("\n⚠️ Native LLM gave a weird response, but it generated text.")

if __name__ == "__main__":
    test_native_llm()
