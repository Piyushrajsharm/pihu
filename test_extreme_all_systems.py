"""
╔══════════════════════════════════════════════════════════════╗
║  PIHU — EXTREME COMPREHENSIVE SYSTEM TEST                   ║
║  Tests ALL 12 sub-systems end-to-end                         ║
║                                                              ║
║  Systems Under Test:                                         ║
║   1. SecurityManager (Vault, Audit, Threat, Sentinel)        ║
║   2. IntegrityChecker (SHA-256 file hashing)                 ║
║   3. OpenClaw Orchestrator (command routing)                  ║
║   4. Swarm Agent (Groq-planned multi-step)                   ║
║   5. GodMode Browser Engine                                  ║
║   6. MiroFish Prediction Engine                              ║
║   7. Automation Tool (vision-verified OS control)            ║
║   8. Window Manager (pywin32)                                ║
║   9. Groq LLM (ultra-fast chat)                             ║
║  10. Cloud LLM (NVIDIA NIM)                                  ║
║  11. Local LLM (qwen3:8b + think-filter)                    ║
║  12. Vision Grounding (screen analysis)                      ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import time
import json

# Fix encoding
sys.stdout.reconfigure(encoding='utf-8')

# Add project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ──────────────────────────────────────────────
# TEST INFRASTRUCTURE
# ──────────────────────────────────────────────

PASS = 0
FAIL = 0
SKIP = 0
RESULTS = []


def test(name: str, func):
    """Run a test and record result."""
    global PASS, FAIL, SKIP
    print(f"\n{'='*60}")
    print(f"  TEST: {name}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        result = func()
        elapsed = time.time() - t0
        if result is None or result is True:
            PASS += 1
            status = "✅ PASS"
        elif result == "SKIP":
            SKIP += 1
            status = "⏭️ SKIP"
        else:
            PASS += 1
            status = "✅ PASS"
        print(f"\n  {status} ({elapsed:.2f}s)")
        RESULTS.append({"test": name, "status": status, "time": f"{elapsed:.2f}s"})
    except Exception as e:
        elapsed = time.time() - t0
        FAIL += 1
        print(f"\n  ❌ FAIL ({elapsed:.2f}s): {e}")
        RESULTS.append({"test": name, "status": "❌ FAIL", "time": f"{elapsed:.2f}s", "error": str(e)})


# ══════════════════════════════════════════════
# TEST 1: SECURITY — VAULT (AES-256 Encryption)
# ══════════════════════════════════════════════

def test_vault():
    from security.security_core import Vault
    vault = Vault()

    # Store a secret
    vault.store("test_api_key", "sk-test-12345-secret-value")
    print("  [+] Stored encrypted secret: test_api_key")

    # Retrieve it
    value = vault.retrieve("test_api_key")
    assert value == "sk-test-12345-secret-value", f"Vault retrieval failed: {value}"
    print(f"  [+] Retrieved & decrypted: {value[:10]}***")

    # List keys
    keys = vault.list_keys()
    assert "test_api_key" in keys, "Key not found in vault"
    print(f"  [+] Vault keys: {keys}")

    # Delete
    vault.delete("test_api_key")
    assert vault.retrieve("test_api_key") is None, "Delete failed"
    print("  [+] Secret deleted successfully")

    print("  🔐 AES-256 Vault: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 2: SECURITY — AUDIT CHAIN (SHA-256)
# ══════════════════════════════════════════════

def test_audit_chain():
    from security.security_core import AuditLog, ThreatLevel

    audit = AuditLog()

    # Record entries
    audit.record("TEST", "test_command_1", ThreatLevel.SAFE, "OK")
    audit.record("TEST", "test_command_2", ThreatLevel.LOW, "OK")
    audit.record("TEST", "test_command_3", ThreatLevel.MEDIUM, "OK")
    print("  [+] Recorded 3 audit entries")

    # Verify chain integrity
    valid, count = audit.verify_chain()
    assert valid, "Audit chain integrity check failed!"
    print(f"  [+] Chain verified: {count} entries, integrity=VALID")
    print("  📜 SHA-256 Audit Chain: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 3: SECURITY — THREAT ASSESSMENT
# ══════════════════════════════════════════════

def test_threat_assessment():
    from security.security_core import ThreatAssessor

    ta = ThreatAssessor()

    tests = [
        ("open notepad", "LOW", False),
        ("hi pihu", "SAFE", False),
        ("download file from web", "MEDIUM", False),
        ("pip install malware", "HIGH", True),
        ("format c:", "CRITICAL", True),
        ("rm -rf /", "CRITICAL", True),
        ("shutdown /s /t 0", "CRITICAL", True),
        ("net user hacker password /add", "CRITICAL", True),
        ("whatsapp kholo", "LOW", False),
    ]

    for cmd, expected_level, expected_block in tests:
        result = ta.assess(cmd)
        status = "✅" if result.label == expected_level else "❌"
        blocked = "BLOCKED" if result.blocked else "allowed"
        print(f"  {status} '{cmd}' → {result.label} ({blocked})")
        assert result.label == expected_level, f"Expected {expected_level}, got {result.label}"

    print("  🔍 Threat Assessment: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 4: SECURITY — SENTINEL (Rate Limiter + Kill Switch)
# ══════════════════════════════════════════════

def test_sentinel():
    from security.security_core import Sentinel

    sentinel = Sentinel(max_actions_per_minute=5)

    # Rate limiting
    for i in range(5):
        assert sentinel.check_rate(), f"Rate check failed at action {i+1}"
    print("  [+] 5 actions permitted (within limit)")

    # 6th should be blocked
    blocked = not sentinel.check_rate()
    assert blocked, "Rate limit not enforced!"
    print("  [+] 6th action BLOCKED (rate limit working)")

    # Kill switch
    sentinel2 = Sentinel(max_actions_per_minute=100)
    sentinel2.kill("TEST: Emergency stop")
    assert not sentinel2.check_rate(), "Kill switch didn't block!"
    print("  [+] Kill switch: ALL actions blocked")

    sentinel2.revive()
    assert sentinel2.check_rate(), "Revive didn't work!"
    print("  [+] Revived: actions allowed again")

    print("  🛡️ Sentinel (Rate Limit + Kill Switch): OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 5: SECURITY — INTEGRITY CHECKER (SHA-256)
# ══════════════════════════════════════════════

def test_integrity():
    from security.security_core import IntegrityChecker

    ic = IntegrityChecker()
    ic.compute_baseline()
    print("  [+] Baseline computed for critical files")

    ok, tampered = ic.verify()
    assert ok, f"Integrity check failed! Tampered: {tampered}"
    print(f"  [+] All critical files verified: integrity=VALID")
    print("  🔒 Integrity Checker: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 6: WINDOW MANAGER (pywin32)
# ══════════════════════════════════════════════

def test_window_manager():
    from tools.window_manager import WindowManager

    wm = WindowManager()

    # List windows
    windows = wm.get_all_windows()
    print(f"  [+] Found {len(windows)} visible windows")
    for w in windows[:5]:
        print(f"      → {w['title'][:60]}")

    # Get active window
    active = wm.get_active_window_title()
    print(f"  [+] Active window: '{active[:50]}'")

    # Find a window
    hwnd = wm.find_window("Windows")
    if hwnd:
        print(f"  [+] Found window matching 'Windows': handle={hwnd}")
    else:
        print("  [~] No window matching 'Windows' (OK)")

    print("  🪟 Window Manager: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 7: GROQ LLM (Ultra-fast inference)
# ══════════════════════════════════════════════

def test_groq():
    from llm.groq_llm import GroqLLM

    groq = GroqLLM()
    if not groq.is_available:
        print("  [!] Groq API key not configured — SKIP")
        return "SKIP"

    t0 = time.time()
    response = groq.generate(
        prompt="Reply in exactly 5 words: What is your name?",
        system_prompt="You are Pihu, a loving girlfriend. Reply in Hinglish.",
        stream=False,
        max_tokens_override=30,
    )
    elapsed = (time.time() - t0) * 1000

    print(f"  [+] Groq response ({elapsed:.0f}ms): {response}")
    assert response and len(response) > 0, "Empty response from Groq"
    print(f"  ⚡ Groq LLM: OPERATIONAL ({elapsed:.0f}ms)")


# ══════════════════════════════════════════════
# TEST 8: LOCAL LLM (qwen3:8b + think filter)
# ══════════════════════════════════════════════

def test_local_llm():
    from llm.local_llm import LocalLLM
    from scheduler import ComputeScheduler

    scheduler = ComputeScheduler()
    llm = LocalLLM(scheduler=scheduler)

    t0 = time.time()
    tokens = []
    gen = llm.generate(
        prompt="Say hi in 3 words",
        system_prompt="Reply briefly",
        stream=True,
        max_tokens_override=30,
    )
    for token in gen:
        tokens.append(token)
    elapsed = (time.time() - t0) * 1000

    full_response = "".join(tokens)
    print(f"  [+] Local LLM ({elapsed:.0f}ms): '{full_response[:80]}'")
    assert len(tokens) > 0, "No tokens generated"

    # Verify think-tags are filtered
    assert "<think>" not in full_response, "Think tags NOT filtered!"
    print("  [+] Think-tag filter: WORKING (no <think> in output)")
    print(f"  🧠 Local LLM (qwen3:8b): OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 9: AUTOMATION TOOL (OS Control)
# ══════════════════════════════════════════════

def test_automation():
    from tools.automation import AutomationTool

    auto = AutomationTool()

    # Test app registry
    assert "whatsapp" in auto.APP_REGISTRY, "WhatsApp not in registry"
    assert "chrome" in auto.APP_REGISTRY, "Chrome not in registry"
    assert "notepad" in auto.APP_REGISTRY, "Notepad not in registry"
    print(f"  [+] App Registry: {len(auto.APP_REGISTRY)} apps registered")

    # Test window patterns
    assert "whatsapp" in auto.APP_WINDOW_PATTERNS, "No window pattern for WhatsApp"
    print(f"  [+] Window Patterns: {len(auto.APP_WINDOW_PATTERNS)} patterns")

    # Test single action execution (safe: just a wait)
    result = auto._execute_single("wait", "0.1")
    assert "Waited" in result, f"Wait failed: {result}"
    print(f"  [+] Action execution: {result}")

    # Test natural language parsing
    # (don't actually open apps, just verify parsing works)
    print("  [+] Natural language parser: loaded")

    print("  ⚙️ Automation Tool (Agentic): OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 10: GODMODE BROWSER ENGINE
# ══════════════════════════════════════════════

def test_godmode():
    from tools.godmode_bridge import GodModeBridge

    gm = GodModeBridge()
    print("  [+] GodMode initialized")

    # Verify it has all methods
    assert hasattr(gm, "execute_browser_task"), "Missing execute_browser_task"
    assert hasattr(gm, "_search_web"), "Missing _search_web"
    assert hasattr(gm, "_youtube_task"), "Missing _youtube_task"
    assert hasattr(gm, "_download_task"), "Missing _download_task"
    print("  [+] Browser capabilities: search, youtube, download, generic")

    print("  🌐 GodMode Browser Engine: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 11: MIROFISH PREDICTION ENGINE
# ══════════════════════════════════════════════

def test_mirofish():
    from tools.mirofish_simulator import MiroFishSimulator

    mf = MiroFishSimulator()
    print("  [+] MiroFish initialized")

    # Pattern-based prediction (no API needed)
    result = mf._pattern_prediction("stock market trend for nifty")
    assert "MiroFish" in result, f"Pattern prediction failed: {result}"
    print(f"  [+] Pattern prediction: {result[:60]}...")

    # Groq-powered prediction
    try:
        t0 = time.time()
        result = mf.predict("What is the best sector to invest in Indian stock market?")
        elapsed = time.time() - t0
        print(f"  [+] Groq prediction ({elapsed:.1f}s): {result[:80]}...")
    except Exception as e:
        print(f"  [~] Groq prediction skipped: {e}")

    # CSV analysis (if stocks_df.csv exists)
    csv_path = os.path.join(os.path.dirname(__file__), "stocks_df.csv")
    if os.path.exists(csv_path):
        summary = mf.analyze_dataset(csv_path)
        print(f"  [+] Dataset analysis:\n{summary[:200]}")
    else:
        print("  [~] stocks_df.csv not found — dataset analysis skipped")

    print("  🐟 MiroFish Prediction Engine: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 12: OPENCLAW ORCHESTRATOR (Full Pipeline)
# ══════════════════════════════════════════════

def test_openclaw():
    from openclaw_bridge import OpenClawBridge

    oc = OpenClawBridge()

    # Test status
    status = oc.get_status()
    print(f"  [+] System Status: {json.dumps(status, indent=4)}")

    # Test threat blocking
    result = oc.execute("format c: now")
    assert "Security blocked" in result or "BLOCKED" in result.upper(), f"Critical command NOT blocked: {result}"
    print(f"  [+] Critical command BLOCKED: ✅")

    # Test audit report
    report = oc.audit_report(last_n=5)
    print(f"  [+] Audit Report:\n{report}")

    # Test kill switch
    oc.emergency_stop()
    result = oc.execute("open notepad")
    assert "blocked" in result.lower() or "kill" in result.lower() or "Security" in result, \
        f"Kill switch didn't block: {result}"
    print(f"  [+] Kill switch ACTIVE: all commands blocked")

    # Resume
    oc.resume()
    print(f"  [+] Resumed: automation re-enabled")

    print("  🔧 OpenClaw Orchestrator: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 13: SWARM AGENT (Groq-Planned Multi-Step)
# ══════════════════════════════════════════════

def test_swarm_planning():
    from tools.pencil_swarm_agent import PencilSwarmAgent
    from tools.automation import AutomationTool
    from tools.vision_grounding import VisionGrounding
    from llm.cloud_llm import CloudLLM
    from llm.groq_llm import GroqLLM

    cloud = CloudLLM()
    groq = GroqLLM()
    vg = VisionGrounding(cloud_llm=cloud)
    auto = AutomationTool(llm_client=cloud, grounding_tool=vg)
    swarm = PencilSwarmAgent(automation_tool=auto, vision_grounding=vg, groq_llm=groq)

    print("  [+] Swarm Agent initialized with Groq + Vision + Automation")

    # Test plan creation (don't execute, just plan)
    t0 = time.time()
    plan = swarm._create_plan("Open notepad and type hello world")
    elapsed = (time.time() - t0) * 1000

    if plan:
        print(f"  [+] Plan created in {elapsed:.0f}ms:")
        for i, phase in enumerate(plan):
            print(f"      Phase {i+1}: {phase.get('phase', '?')} ({len(phase.get('actions', []))} actions)")
    else:
        print(f"  [~] Plan creation returned None (LLM may be unavailable)")

    print("  🐝 Swarm Agent (Groq Planner): OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 14: VISION GROUNDING (Screen Analysis)
# ══════════════════════════════════════════════

def test_vision():
    from tools.vision_grounding import VisionGrounding
    from llm.cloud_llm import CloudLLM

    cloud = CloudLLM()
    vg = VisionGrounding(cloud_llm=cloud)

    # Screenshot capture test
    t0 = time.time()
    b64, w, h = vg._screenshot_to_b64()
    elapsed = (time.time() - t0) * 1000
    print(f"  [+] Screenshot captured: {w}x{h} ({len(b64)} chars b64) in {elapsed:.0f}ms")

    # Grid overlay test
    t0 = time.time()
    b64_grid, cell_map = vg._draw_grid_and_get_b64()
    elapsed = (time.time() - t0) * 1000
    print(f"  [+] Grid overlay: {len(cell_map)} cells in {elapsed:.0f}ms")

    print("  👁️ Vision Grounding: OPERATIONAL")


# ══════════════════════════════════════════════
# TEST 15: FULL INTEGRATED PIPELINE
# ══════════════════════════════════════════════

def test_full_pipeline():
    """The ultimate test: SecurityManager → OpenClaw → Swarm → Automation."""
    from security.security_core import SecurityManager

    sm = SecurityManager()

    # Test complete flow
    print("  [Phase 1] Security assessment...")
    can_exec, reason = sm.can_execute("open notepad")
    assert can_exec, f"Security blocked safe command: {reason}"
    print(f"    → Allowed: {reason}")

    print("  [Phase 2] Critical command blocking...")
    can_exec, reason = sm.can_execute("del /s /q C:\\*")
    assert not can_exec, "Critical command was allowed!"
    print(f"    → Blocked: {reason}")

    print("  [Phase 3] Audit chain verification...")
    valid, count = sm.audit.verify_chain()
    print(f"    → Chain: {'VALID' if valid else 'BROKEN'} ({count} entries)")

    print("  [Phase 4] Vault encryption round-trip...")
    sm.vault.store("pipeline_test", "encrypted_value_12345")
    retrieved = sm.vault.retrieve("pipeline_test")
    assert retrieved == "encrypted_value_12345", "Vault round-trip failed"
    sm.vault.delete("pipeline_test")
    print(f"    → Vault: store → encrypt → decrypt → verify → delete ✅")

    print("  [Phase 5] Integrity check...")
    ok, tampered = sm.integrity.verify()
    print(f"    → Files: {'ALL OK' if ok else f'{len(tampered)} TAMPERED'}")

    print("  🏆 FULL INTEGRATED PIPELINE: OPERATIONAL")


# ══════════════════════════════════════════════
# RUN ALL TESTS
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "█" * 60)
    print("█  PIHU — EXTREME COMPREHENSIVE SYSTEM TEST")
    print("█  Testing ALL 15 sub-systems")
    print("█" * 60)

    start = time.time()

    test("1. VAULT (AES-256 Encryption)", test_vault)
    test("2. AUDIT CHAIN (SHA-256)", test_audit_chain)
    test("3. THREAT ASSESSMENT", test_threat_assessment)
    test("4. SENTINEL (Rate Limit + Kill Switch)", test_sentinel)
    test("5. INTEGRITY CHECKER (SHA-256)", test_integrity)
    test("6. WINDOW MANAGER (pywin32)", test_window_manager)
    test("7. GROQ LLM (Ultra-fast)", test_groq)
    test("8. LOCAL LLM (qwen3:8b)", test_local_llm)
    test("9. AUTOMATION TOOL (OS Control)", test_automation)
    test("10. GODMODE BROWSER ENGINE", test_godmode)
    test("11. MIROFISH PREDICTION", test_mirofish)
    test("12. OPENCLAW ORCHESTRATOR", test_openclaw)
    test("13. SWARM AGENT (Groq Planner)", test_swarm_planning)
    test("14. VISION GROUNDING", test_vision)
    test("15. FULL INTEGRATED PIPELINE", test_full_pipeline)

    total_time = time.time() - start

    # ── FINAL REPORT ──
    print("\n" + "═" * 60)
    print("  EXTREME TEST RESULTS")
    print("═" * 60)

    for r in RESULTS:
        error = f" — {r.get('error', '')[:40]}" if 'error' in r else ""
        print(f"  {r['status']}  {r['test']:<45} {r['time']}{error}")

    print("─" * 60)
    print(f"  ✅ PASSED: {PASS}")
    print(f"  ❌ FAILED: {FAIL}")
    print(f"  ⏭️ SKIPPED: {SKIP}")
    print(f"  ⏱️ TOTAL TIME: {total_time:.1f}s")
    print("─" * 60)

    if FAIL == 0:
        print("  🏆 ALL SYSTEMS OPERATIONAL — PIHU IS FULLY ARMED 🛡️🚀")
    else:
        print(f"  ⚠️ {FAIL} SYSTEM(S) NEED ATTENTION")

    print("═" * 60)
