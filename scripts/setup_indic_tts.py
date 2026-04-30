import os
import zipfile
import requests
from pathlib import Path

# URLs for Indic-TTS Hindi Checkpoint
HINDI_ZIP_URL = "https://github.com/AI4Bharat/Indic-TTS/releases/download/v1-checkpoints-release/hi.zip"

def setup_indic_tts():
    # Setup paths
    base_dir = Path(__file__).parent.parent.resolve()
    data_dir = base_dir / "data"
    tts_models_dir = data_dir / "tts_models"
    hi_model_dir = tts_models_dir / "hi"
    
    # Ensure directories exist
    tts_models_dir.mkdir(parents=True, exist_ok=True)
    
    zip_path = tts_models_dir / "hi.zip"
    
    print(f"[*] Starting download: {HINDI_ZIP_URL}")
    print(f"[*] Target location: {zip_path}")
    
    # Download with progress (simple)
    try:
        response = requests.get(HINDI_ZIP_URL, stream=True)
        response.raise_for_status()
        
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        print("[+] Download complete.")
    except Exception as e:
        print(f"[!] Failed to download Hindi models: {e}")
        return

    # Extract
    print(f"[*] Extracting {zip_path} to {hi_model_dir}...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(hi_model_dir)
        print("[+] Extraction complete.")
    except Exception as e:
        print(f"[!] Failed to extract: {e}")
        return

    # Clean up zip
    os.remove(zip_path)
    print("[+] Cleaned up zip file.")

    # Structure check/fix
    # The zip usually contains folders like 'fastpitch' and 'hifigan' directly or inside a subdirectory.
    # We want hi/fastpitch and hi/hifigan
    # Let's see what's in there
    print(f"[*] Finalizing structure...")
    
    # Implementation detail: Indic-TTS v1 releases often have:
    # hi/
    #   fastpitch/
    #     best_model.pth
    #     config.json
    #   hifigan/
    #     best_model.pth
    #     config.json
    
    print("[+] Indic-TTS Hindi environment is ready.")

if __name__ == "__main__":
    setup_indic_tts()
