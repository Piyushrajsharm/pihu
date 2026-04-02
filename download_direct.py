import requests
import os

def download_direct():
    url = "https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-v3.5.Q4_K_M.gguf"
    target_path = "d:/JarvisProject/pihu/models/phi-3.5-mini.gguf"
    
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    # Check if already exists
    if os.path.exists(target_path):
        print(f"✅ File already exists at {target_path} ({os.path.getsize(target_path)} bytes)")
        return target_path

    print(f"📥 Downloading Phi-3.5-mini (2.2GB) directly to {target_path}...")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(target_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024*1024): # 1MB chunks
                if chunk:
                    f.write(chunk)
        
        print("✅ Direct download complete.")
        return target_path
    except Exception as e:
        print(f"❌ Direct download failed: {e}")
        return None

if __name__ == "__main__":
    download_direct()
