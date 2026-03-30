import time
import requests
import json
from config import NVIDIA_NIM_API_KEY, NVIDIA_NIM_BASE_URL, CLOUD_LLM_MODEL

def test_stream():
    headers = {
        "Authorization": f"Bearer {NVIDIA_NIM_API_KEY}",
        "Accept": "text/event-stream"
    }
    payload = {
        "model": "meta/llama-3.1-8b-instruct",
        "messages": [
            {"role": "system", "content": "You are a fast assistant. Reply with exactly two words."},
            {"role": "user", "content": "Hello!"}
        ],
        "max_tokens": 50,
        "stream": True,
        "temperature": 1.0,
        "top_p": 1.0
    }
    
    t0 = time.time()
    try:
        print(f"[{time.time()-t0:.2f}s] Sending request to {CLOUD_LLM_MODEL}...")
        response = requests.post(
            f"{NVIDIA_NIM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=30
        )
        print(f"[{time.time()-t0:.2f}s] Got Headers. Status Code: {response.status_code}")
        
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if token:
                            print(f"[{time.time()-t0:.2f}s] Token: '{token}'")
                    except Exception as e:
                        pass
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_stream()
