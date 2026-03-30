"""Test NVIDIA NIM Cloud Vision API directly."""
import requests
import base64
from PIL import Image
import io
from config import NVIDIA_NIM_API_KEY, NVIDIA_NIM_BASE_URL

# Prepare a small test image
img = Image.open("Gemini_Generated_Image_55zeon55zeon55ze.png")
img = img.convert("RGB").resize((256, 144))
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=60)
img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
print(f"Image payload: {len(img_b64)} chars")

# Try different vision model names
models_to_try = [
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct", 
    "nvidia/vila-1.5-13b",
    "microsoft/phi-3.5-vision-instruct",
]

headers = {
    "Authorization": f"Bearer {NVIDIA_NIM_API_KEY}",
    "Accept": "application/json",
}

for model in models_to_try:
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this image? One sentence only."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ],
        }],
        "max_tokens": 100,
        "stream": False,
    }
    
    try:
        r = requests.post(f"{NVIDIA_NIM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            text = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"✅ {model}: {text[:100]}")
            break
        else:
            print(f"❌ {model}: HTTP {r.status_code} - {r.text[:80]}")
    except Exception as e:
        print(f"❌ {model}: {e}")
