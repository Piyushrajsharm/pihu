"""Quick test: Does gemma3:1b support vision (image input)?"""
import ollama
from PIL import Image
import io

# Load and resize image to something small
img = Image.open("Gemini_Generated_Image_55zeon55zeon55ze.png")
img = img.convert("RGB").resize((512, 288))
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=70)
img_bytes = buf.getvalue()
print(f"Image size: {len(img_bytes)/1024:.0f} KB")

client = ollama.Client(host="http://localhost:11434")
try:
    r = client.chat(
        model="gemma3:1b",
        messages=[{
            "role": "user",
            "content": "What do you see in this image? Describe briefly.",
            "images": [img_bytes],
        }],
    )
    print("Response:", r.get("message", {}).get("content", "NO CONTENT"))
except Exception as e:
    print(f"ERROR: {e}")
    print("\ngemma3:1b may not support vision. Checking model info...")
    try:
        info = client.show("gemma3:1b")
        families = info.get("details", {}).get("families", [])
        print(f"Model families: {families}")
        print(f"Supports vision: {'vision' in str(families).lower()}")
    except:
        print("Could not get model info")
