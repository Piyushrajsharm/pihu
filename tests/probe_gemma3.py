import ollama

def probe_gemma3_format():
    print("Probing gemma3n:e2b manual tool-calling format...")
    
    prompt = """You have access to a tool called 'execute_python'.
If the user asks for a calculation or execution, call the tool like this:
CALL: execute_python(code="print('hello')")

User: Calculate 99 * 88 using python.
"""
    
    try:
        response = ollama.chat(
            model='gemma3n:e2b',
            messages=[{'role': 'user', 'content': prompt}],
            stream=False
        )
        print("Raw Response:")
        print("-" * 30)
        print(response['message']['content'])
        print("-" * 30)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probe_gemma3_format()
