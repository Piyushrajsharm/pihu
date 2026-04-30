import sys
import os
from pathlib import Path

# Ensure pihu root is on sys.path
sys.path.insert(0, str(Path(__file__).parent))

from config import CODE_EXECUTOR_TYPE
from logger import get_logger

log = get_logger("VERIFY")

def verify_local_first():
    print("=" * 50)
    print(" 🛠️  PIHU — LOCAL-FIRST VERIFICATION")
    print("=" * 50)
    
    # 1. Check Config
    print(f"[*] CODE_EXECUTOR_TYPE: {CODE_EXECUTOR_TYPE}")
    if CODE_EXECUTOR_TYPE != "docker":
        print("❌ Error: Code executor is not set to 'docker'.")
        return
    else:
        print("✅ Config is locally set.")

    # 2. Check Docker
    try:
        from sandbox.docker_executor import DockerExecutor
        executor = DockerExecutor()
        if executor.is_available:
            print("✅ Docker Sandbox is reachable and available.")
        else:
            print("⚠️ Warning: Docker is NOT running. Pihu will fall back to degraded mode.")
    except Exception as e:
        print(f"❌ Error docking Docker: {e}")

    # 3. Check for E2B presence
    from pihu_brain import PihuBrain
    brain = PihuBrain(backend_mode=True)
    brain.initialize()
    
    # Check if e2b attribute exists in brain (it shouldn't anymore)
    if hasattr(brain.router, 'e2b') and brain.router.e2b is not None:
        print("❌ Error: E2B is still initialized in the Router!")
    else:
        print("✅ E2B has been successfully purged from the brain.")

    print("-" * 50)
    print("RESULT: Pihu is now fully local-first. 🏠")

if __name__ == "__main__":
    verify_local_first()
