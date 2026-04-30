import ollama
import json

def test_gemma3_tool_calling():
    print("Testing gemma3n:e2b tool-calling via Ollama...")
    
    tools = [{
        'type': 'function',
        'function': {
            'name': 'execute_python',
            'description': 'Execute Python code',
            'parameters': {
                'type': 'object',
                'properties': {
                    'code': {'type': 'string'},
                },
                'required': ['code'],
            },
        },
    }]

    try:
        response = ollama.chat(
            model='gemma3n:e2b',
            messages=[{'role': 'user', 'content': 'Calculate 1234 * 5678 using python.'}],
            tools=tools
        )
        
        msg = response.get('message', {})
        if msg.get('tool_calls'):
            print("✅ Tool call detected!")
            for tool in msg['tool_calls']:
                print(f"Tool: {tool['function']['name']}")
                print(f"Args: {tool['function']['arguments']}")
        else:
            print("❌ No tool call detected.")
            print(f"Response: {msg.get('content', '')}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_gemma3_tool_calling()
