import sys
import os
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from security.security_core import AtomicNonceGenerator, Vault, AuditLog, Sentinel
from openclaw_bridge import OpenClawBridge
from tools.pencil_swarm_agent import PencilSwarmAgent
from tools.automation import AutomationTool

print("="*60)
print("  RING 0 LEVEL PARADIGM TEST")
print("="*60)

# TEST 1: ATOMIC NONCES
print("\n[1] Testing Atomic Nonce Uniqueness under iteration burst...")
nonces = set()
collision = False
for _ in range(5000):
    n = AtomicNonceGenerator.generate()
    if n in nonces:
        collision = True
    nonces.add(n)
print(f"  → 5000 nonces generated. Collisions: {'YES' if collision else 'NONE'}")
print(f"  → Nonce format sample: {list(nonces)[0].hex()}")

# TEST 2: VAULT DPAPI & RAM SCRUBBING
print("\n[2] Testing DPAPI Vault Lifecycle & RAM scrub resilience...")
vault = Vault()
vault.store("ring0_test", "supersecret")
print(f"  → Restored value: {vault.retrieve('ring0_test')}")

# TEST 3: REGISTRY ANCHOR
print("\n[3] Testing OS Registry Anchoring...")
audit = AuditLog()
action_cmd = "test_anchor_" + str(int(time.time()))
audit.record("ANCHOR_TEST", action_cmd, 0)
val = audit._get_registry_anchor()
print(f"  → Registry OS Hash written: {val[:16]}..." if val else "  → Registry OS Hash FAILED")

# TEST 4: SANDBOXING / DRY RUN
print("\n[4] Testing OS Sandboxing via OpenClaw...")
auto = AutomationTool()
swarm = PencilSwarmAgent(automation_tool=auto, vision_grounding=None)
oc = OpenClawBridge(swarm_agent=swarm, automation=auto)

print("  → Executing 'open notepad' in DRY RUN mode...")
result = oc.execute("open notepad", dry_run=True)
print(f"  → Sandbox Result: {result}")

print("\n🏆 RING 0 TEST COMPLETED")
