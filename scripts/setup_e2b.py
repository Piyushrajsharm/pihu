import sys
import os
from pathlib import Path

# Ensure pihu root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from security.security_core import SecurityManager
from logger import get_logger

log = get_logger("SETUP")

def setup_e2b():
    print("=" * 50)
    print(" 🛠️  PIHU — E2B SETUP")
    print("=" * 50)
    print("E2B provides a secure cloud sandbox for Pihu to run code.")
    print("Get your API key at: https://e2b.dev/docs")
    print("-" * 50)
    
    api_key = input("🔑 Enter your E2B_API_KEY: ").strip()
    
    if not api_key:
        print("❌ Error: API key cannot be empty.")
        return

    try:
        sec = SecurityManager()
        # Store in the encrypted vault
        sec.secret_broker.store("E2B_API_KEY", api_key)
        
        print("\n✅ Success! E2B_API_KEY has been securely stored in the Pihu Vault.")
        print("Pihu can now use Gemma 3 with the E2B Code Interpreter.")
    except Exception as e:
        print(f"\n❌ Failed to store secret: {e}")

if __name__ == "__main__":
    setup_e2b()
