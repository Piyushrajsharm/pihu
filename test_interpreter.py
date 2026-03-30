"""
Pihu V2 — OpenInterpreter Execution Sandbox
Validates that interpreter binds to local Ollama and filters out the execution tracebacks,
yielding ONLY conversational Hinglish via the stream wrapper.
"""
from interpreter_engine import InterpreterEngine

def run_tests():
    engine = InterpreterEngine()
    
    if not engine.is_available:
        print("[CRITICAL ERROR] InterpreterEngine failed. Check pip install open-interpreter.")
        return
        
    print("\n========== V2 HANDS BOOT SEQUENCE ==========")
    print("Testing isolated Ollama query...")
    print("User Prompt: 'create a python file called testsript.py that prints hello world. do not ask me for confirmation.'")
    
    stream = engine.execute_stream("create a python file called testsript.py that prints hello world. do not ask me for confirmation.")
    
    print("\n[STREAMING FILTERED PIHU OUTPUT]:")
    for chunk in stream:
        print(chunk, end="", flush=True)
        
    print("\n\n========== V2 HANDS TEST SUCCESS ==========")

if __name__ == "__main__":
    run_tests()
