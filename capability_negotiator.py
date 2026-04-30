"""
Pihu — Capability Negotiator
Evaluates the semantic depth of the currently loaded model vs hardware layout.
Determines whether Pihu can handle complex structural logic (JSON UI generation, multi-agent swarms)
or must gracefully degrade to simple text operations.
"""

from typing import Dict, Any
from logger import get_logger

log = get_logger("CAPABILITY")

class CapabilityNegotiator:
    """Gatekeeper for complex AI logic routing."""

    def __init__(self, hardware_profile=None):
        self.hardware_profile = hardware_profile
        self.matrix = {
            "json_mode": True,
            "swarm_capable": True,
            "complex_reasoning": True
        }
        
    def evaluate_model(self, model_name: str, llm_client=None) -> Dict[str, bool]:
        """Calculates capacities either via hardware limits or empirical probing."""
        name_lower = model_name.lower()
        
        # Forced hardware-based constraints (Tier 1 inherently blocks complex actions)
        if self.hardware_profile and self.hardware_profile.tier == 1:
            log.warning("Tier 1 Hardware constraint locking capability matrix to degraded mode.")
            self.matrix["json_mode"] = False
            self.matrix["swarm_capable"] = False
            self.matrix["complex_reasoning"] = False
            return self.matrix
            
        # Phase 7: Live Synthetic Probing for Tier 2+
        if llm_client:
            log.info("🧪 [CAPABILITY] Running Synthetic JSON Benchmark on %s...", model_name)
            passed = self._run_synthetic_benchmark(llm_client)
            
            if passed:
                log.info("✅ Model %s PASSED benchmark. Structural capabilities unlocked.", model_name)
                self.matrix["json_mode"] = True
                self.matrix["swarm_capable"] = True
                self.matrix["complex_reasoning"] = True
            else:
                log.warning("❌ Model %s FAILED benchmark. Structural capabilities disabled.", model_name)
                self.matrix["json_mode"] = False
                self.matrix["swarm_capable"] = False
                self.matrix["complex_reasoning"] = False
        else:
            # Fallback to string heuristics if no client attached
            log.warning("No LLM client provided for probing, falling back to heuristics.")
            is_sub_7b = any(trigger in name_lower for trigger in ["phi3", "3b", "1b", "2b", "gemma", "mini"])
            if is_sub_7b:
                self.matrix["json_mode"] = False
                self.matrix["swarm_capable"] = False
                self.matrix["complex_reasoning"] = False
            else:
                self.matrix["json_mode"] = True
                self.matrix["swarm_capable"] = True
                self.matrix["complex_reasoning"] = True
            
        return self.matrix
        
    def _run_synthetic_benchmark(self, llm_client) -> bool:
        """Fires a strict structural test at the model to verify JSON obedience."""
        sys_prompt = "You are a benchmark tester. Output ONLY raw JSON."
        prompt = "Return exactly this JSON object and nothing else: {\"status\": \"passed\", \"test\": [1,2,3]}"
        
        try:
            # Ensure generate_sync or stream=False is used
            # Model Provider Layer standardizes this. We use generate with stream=False
            response = llm_client.generate(
                prompt=prompt,
                system_prompt="Return JSON only.",
                stream=False,
                max_tokens_override=50,
                memory_override=False,
                timeout=10
            )
            
            if not response:
                return False
                
            stripped = response.strip()
            import re
            # Remove markdown JSON wrappers if LLM hallucinated them
            if stripped.startswith("```"):
                stripped = re.sub(r"^```(?:json)?\n?", "", stripped)
                stripped = re.sub(r"\n?```$", "", stripped)
                
            import json
            data = json.loads(stripped)
            
            if data.get("status") == "passed" and data.get("test") == [1, 2, 3]:
                return True
            return False
            
        except Exception as e:
            log.debug("Synthetic benchmark threw exception: %s", e)
            return False
        
    def can_generate_ui(self) -> bool:
        return self.matrix.get("json_mode", False)
        
    def can_run_swarm(self) -> bool:
        return self.matrix.get("swarm_capable", False)

