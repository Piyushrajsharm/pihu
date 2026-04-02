from huggingface_hub import hf_hub_download
import os

def download_phi():
    print("📥 Downloading Phi-3.5-mini-instruct (Q4_K_M GGUF)...")
    repo_id = "bartowski/Phi-3.5-mini-instruct-GGUF"
    filename = "Phi-3.5-mini-instruct-v3.5.Q4_K_M.gguf"
    local_dir = "d:/JarvisProject/pihu/models"
    
    os.makedirs(local_dir, exist_ok=True)
    
    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=local_dir,
            local_dir_use_symlinks=False
        )
        print(f"✅ Download complete: {path}")
    except Exception as e:
        print(f"❌ Download failed: {e}")

if __name__ == "__main__":
    download_phi()
