"""
Pihu — Telemetry Core (Real Usage Logging)
Silently tracks daily-driver failures, successes, context misses, and macro initiations
for the Weekly Review protocol without blocking standard latency.
"""

import json
import time
from pathlib import Path
from config import MEMORY_DIR
from logger import get_logger

log = get_logger("TELEMETRY")

class TelemetryCore:
    def __init__(self):
        self.log_file = Path(MEMORY_DIR) / "telemetry.jsonl"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
    def log_event(self, event_type: str, detail: str = ""):
        """Appends a JSONL string representing an architectural interaction boundary."""
        from config import MAX_TELEMETRY_DETAIL_LENGTH
        payload = {
            "timestamp": time.time(),
            "event": event_type, # "SUCCESS", "SURRENDER", "CONTEXT_MISS", "MACRO_PROPOSED"
            "detail": detail[:MAX_TELEMETRY_DETAIL_LENGTH] # Truncated to prevent VRAM destruction during weekly review
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
            log.info("Telemetry event recorded: %s", event_type)
        except Exception as e:
            log.error("Failed to write telemetry: %s", e)

    def get_weekly_summary(self) -> str:
        """Reads the last 7 days of raw telemetry and compresses it tightly for the review prompt."""
        if not self.log_file.exists(): 
            return "No telemetry data exists yet. The user hasn't used the system."
        
        now = time.time()
        week_ago = now - (7 * 24 * 3600)
        
        totals = {"SUCCESS": 0, "SURRENDER": 0, "CONTEXT_MISS": 0, "MACRO_PROPOSED": 0}
        recent_fails = []
        
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                        
                    if data.get("timestamp", 0) >= week_ago:
                        ev = data.get("event")
                        if ev in totals:
                            totals[ev] += 1
                        if ev in ["SURRENDER", "CONTEXT_MISS"]:
                            dt = data.get("detail", "")
                            if dt and dt not in recent_fails: 
                                recent_fails.append(dt)
        except Exception as e:
            log.error("Failed to read telemetry: %s", e)
            return "Error reading telemetry file."
            
        # Format the context block natively for the LLM inference
        summary = (
            f"TELEMETRY METRICS (LAST 7 DAYS):\n"
            f"- Bug Fixes Concluded Successfully (Solves): {totals['SUCCESS']}\n"
            f"- Infinite Loop Surrenders (Where you gave up/Failed completely): {totals['SURRENDER']}\n"
            f"- Context Misses (User angrily stated you misunderstood the problem): {totals['CONTEXT_MISS']}\n"
            f"- Automation Macros Iterated: {totals['MACRO_PROPOSED']}\n\n"
        )
        if recent_fails:
            summary += f"Recent Physical Failure Samples:\n- " + "\n- ".join(recent_fails[-5:])
            
        return summary
