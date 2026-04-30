import subprocess
import json

def cleanup_and_pull():
    print("=" * 50)
    print(" 🧹 OLLAMA CLEANUP & UPGRADE")
    print("=" * 50)
    
    # 1. Get list of models
    print("[*] Fetching existing models...")
    try:
        # We use 'ollama list' and parse it
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ Error: Ollama is not running.")
            return

        lines = result.stdout.strip().split("\n")[1:] # Skip header
        models = [line.split()[0] for line in lines if line.strip()]
        
        if not models:
            print("✅ No models found to delete.")
        else:
            print(f"[*] Found {len(models)} models: {', '.join(models)}")
            
            # 2. Delete all models
            for model in models:
                print(f"[-] Deleting {model}...")
                subprocess.run(["ollama", "rm", model], capture_output=True)
            print("✅ All existing models cleared.")

    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        return

    # 3. Pull the new model
    new_model = "llama3.2:3b"
    print(f"\n[*] Pulling NEW model: {new_model} ...")
    print("    (This might take a few minutes depending on your internet)")
    
    try:
        # Run pull interactively so user can see progress (using subprocess.run without capture)
        subprocess.run(["ollama", "pull", new_model], check=True)
        print(f"\n✅ SUCCESS! {new_model} is ready for Pihu.")
    except Exception as e:
        print(f"❌ Pull failed: {e}")

if __name__ == "__main__":
    cleanup_and_pull()
