import os
import urllib.request
import zipfile
import shutil
from pathlib import Path

# Paths
BASE_DIR = Path("d:/JarvisProject/pihu")
THIRD_PARTY_DIR = BASE_DIR / "third_party"
TTS_DIR = THIRD_PARTY_DIR / "TTS"
ZIP_PATH = THIRD_PARTY_DIR / "TTS_master.zip"

THIRD_PARTY_DIR.mkdir(parents=True, exist_ok=True)

# URL for gokulkarthik's fork
URL = "https://github.com/gokulkarthik/TTS/archive/refs/heads/master.zip"

def download_tts():
    print(f"Downloading TTS source from {URL}...")
    try:
        urllib.request.urlretrieve(URL, str(ZIP_PATH))
        print("Download complete.")
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False

def extract_and_install():
    print("Extracting TTS...")
    with zipfile.ZipFile(str(ZIP_PATH), 'r') as zip_ref:
        zip_ref.extractall(str(THIRD_PARTY_DIR))

    # The zip usually extracts a folder called 'TTS-master'
    extracted_folder = THIRD_PARTY_DIR / "TTS-master"
    if extracted_folder.exists():
        if TTS_DIR.exists():
            shutil.rmtree(TTS_DIR)
        extracted_folder.rename(TTS_DIR)
        print(f"Extracted to {TTS_DIR}.")
    else:
        print("Expected TTS-master folder not found in extraction directory!")
        return

    # Delete the zip file
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

if __name__ == "__main__":
    if download_tts():
        extract_and_install()
