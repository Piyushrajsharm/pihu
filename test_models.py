import requests
from config import NVIDIA_NIM_API_KEY, NVIDIA_NIM_BASE_URL

def check_models():
    headers = {"Authorization": f"Bearer {NVIDIA_NIM_API_KEY}"}
    try:
        response = requests.get(f"{NVIDIA_NIM_BASE_URL}/models", headers=headers, timeout=10)
        models = response.json().get("data", [])
        for m in models:
            m_id = m.get("id", "").lower()
            if any(k in m_id for k in ["vision", "multimodal", "phi-3", "llama-3.2-vision", "vila", "cogvlm"]):
                print(m.get("id"))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    check_models()
