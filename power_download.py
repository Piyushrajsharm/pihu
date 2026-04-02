import os
import sys
import shutil
import time
from huggingface_hub import hf_hub_download

def power_download():
    repo_id = "bartowski/Phi-3.5-mini-instruct-GGUF"
    filename = "Phi-3.5-mini-instruct-Q4_K_M.gguf"
    target_dir = r"D:\JarvisProject\pihu\models"
    target_path = os.path.join(target_dir, filename)
    
    os.makedirs(target_dir, exist_ok=True)
    
    print(f"🚀 [POWER DOWNLOAD] Target: {target_path}")
    
    try:
        # Download (will resume if partial file exists)
        cache_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            resume_download=True,
            force_download=False,
        )
        
        print(f"📦 [POWER DOWNLOAD] Cached at: {cache_path}")
        
        # Move to target if not already there
        if os.path.exists(cache_path) and not os.path.exists(target_path):
            print(f"🚚 [POWER DOWNLOAD] Copying to workspace...")
            shutil.copy2(cache_path, target_path)
            print("✅ [POWER DOWNLOAD] Done!")
        elif os.path.exists(target_path):
            print("✅ [POWER DOWNLOAD] File already in workspace.")
            
    except Exception as e:
        print(f"❌ [POWER DOWNLOAD] Error: {e}")
        # Auto-retry in 10 seconds?
        time.sleep(10)
        sys.exit(1)

if __name__ == "__main__":
    power_download()
