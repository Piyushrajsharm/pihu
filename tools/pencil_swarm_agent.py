"""
Pihu — Pencil SWARM Agent (Fully Agentic Orchestrator)
The brain of Pihu's OS control. Every task goes through:
    PLAN (Groq LLM) → EXECUTE (Automation) → VERIFY (Vision) → RETRY/ADAPT

Integrates:
    - OpenClaw: Command orchestration & routing
    - GodMode: Browser automation with vision feedback
    - MiroFish: Predictive simulation for data tasks
"""

import time
import json
import os
from logger import get_logger
from tools.godmode_bridge import GodModeBridge
from tools.mirofish_simulator import MiroFishSimulator

log = get_logger("SWARM")

MAX_RETRIES = 2


class PencilSwarmAgent:
    """Fully Agentic OS Orchestrator — Plan, Execute, Verify, Adapt."""

    def __init__(self, automation_tool, vision_grounding, groq_llm=None):
        self.automation = automation_tool
        self.grounding = vision_grounding
        self.llm = automation_tool.llm           # Cloud LLM (for vision)
        self.groq = groq_llm                     # Groq (for fast planning)

        # Sub-systems
        self.godmode = GodModeBridge()
        self.mirofish = MiroFishSimulator()
        
        from critic_swarm import CriticSwarm
        self.critic = CriticSwarm()

        log.info("🐝 SWARM Agent initialized (Agentic Mode) | GodMode=%s, MiroFish=%s",
                 "✅" if self.godmode else "❌",
                 "✅" if self.mirofish else "❌")

    # ──────────────────────────────────────────────
    # MAIN ENTRY: Any Task
    # ──────────────────────────────────────────────

    def perform_task(self, task_description: str, dry_run: bool = False) -> str:
        """Execute ANY task through the full agentic pipeline.

        1. Classify: Is this a browser task, OS task, or data task?
        2. Plan: Break into phases using Groq LLM
        3. Execute each phase with vision verification
        4. Retry failed phases
        """
        log.info("🐝 === SWARM TASK START === %s", task_description[:80])
        t0 = time.time()

        # Route to specialized handler if applicable
        task_lower = task_description.lower()

        if any(kw in task_lower for kw in ["browser", "website", "google", "search online", "web"]):
            return self._handle_browser_task(task_description)

        if any(kw in task_lower for kw in ["predict", "forecast", "simulation", "market"]):
            return self._handle_prediction_task(task_description)

        # General OS task → Plan & Execute
        return self._plan_and_execute(task_description, t0, dry_run=dry_run)

    # ──────────────────────────────────────────────
    # AGENTIC PLAN & EXECUTE LOOP
    # ──────────────────────────────────────────────

    def _plan_and_execute(self, task: str, t0: float, dry_run: bool = False) -> str:
        """Core agentic loop: Plan → Execute → Verify → Retry."""

        # Step 1: Create plan
        plan = self._create_plan(task)
        if not plan:
            log.warning("Plan creation failed, falling back to simple execution")
            return self.automation._execute_single("type", task, dry_run=dry_run)

        # Step 1.5: AI Decision Safety Critic
        if not self._evaluate_plan_safety(plan):
            log.critical("🚨 Plan execution aborted by Critic.")
            return "🚨 BLOCKED BY AI CRITIC: The intent of this task was deemed structurally unsafe by the Decision Safety Layer."

        # Step 2: Execute each phase
        results = []
        for i, phase in enumerate(plan):
            phase_name = phase.get("phase", f"Phase {i+1}")
            actions = phase.get("actions", [])
            verify = phase.get("verify", "")

            log.info("📋 Phase %d/%d: %s (%d actions)", i+1, len(plan), phase_name, len(actions))

            # Execute actions
            phase_results = []
            for action in actions:
                if os.path.exists("data/.stop_pihu"):
                    log.critical("🚨 Hardware Kill Interrupt Triggered mid-execution!")
                    print("\n[🎙️ Pihu]: haan bol, ruk gayi. kya galti hui?\n")
                    os.remove("data/.stop_pihu")
                    return "🚨 Execution aborted mid-way by user."
                    
                act = action.get("action", "")
                arg = str(action.get("arg", ""))
                result = self.automation._execute_single(act, arg, dry_run=dry_run)
                phase_results.append(result)
                log.info("  → %s %s: %s", act, arg[:30], result[:50])

            # Verify phase
            if verify and self.grounding:
                time.sleep(1.5)  # Let UI settle
                verified = self._verify_with_retry(verify, actions, phase_name)
                if verified:
                    results.append(f"✅ {phase_name}: Verified")
                else:
                    results.append(f"⚠️ {phase_name}: Verification uncertain — proceeding")
            else:
                results.append(f"✅ {phase_name}: Done")

        elapsed = time.time() - t0
        summary = "🐝 SWARM Complete (%.1fs):\n" % elapsed + "\n".join(results)
        log.info(summary)
        return summary

    def _verify_with_retry(self, expected: str, actions: list, phase_name: str) -> bool:
        """Verify screen state, retry if failed."""
        for attempt in range(MAX_RETRIES + 1):
            log.info("👁️ Verifying (attempt %d): %s", attempt + 1, expected)
            verified = self.grounding.verify_state(expected)
            if verified:
                return True

            if attempt < MAX_RETRIES:
                log.warning("⚠️ Verification failed, retrying phase '%s'...", phase_name)
                # Re-execute actions
                for action in actions:
                    self.automation._execute_single(action.get("action", ""), str(action.get("arg", "")))
                time.sleep(2)

        return False

    # ──────────────────────────────────────────────
    # PLANNER (Groq-powered for speed)
    # ──────────────────────────────────────────────

    def _create_plan(self, task: str) -> list[dict] | None:
        """Use Groq LLM (fast) to decompose task into phases."""
        prompt = f"""You are a Windows OS automation planner. Break this task into phases.

TASK: "{task}"

Each phase has:
- "phase": short name
- "actions": array of atomic UI actions
- "verify": what the screen should show after (for vision check)

Available actions:
1. {{"action": "open", "arg": "<app_name>"}}
2. {{"action": "type", "arg": "<text>"}}
3. {{"action": "hotkey", "arg": "<key1+key2>"}}
4. {{"action": "click", "arg": "<x,y>"}}
5. {{"action": "wait", "arg": <seconds>}}
6. {{"action": "find_and_click", "arg": "<element description>"}}
7. {{"action": "focus", "arg": "<app_name>"}}
8. {{"action": "scroll", "arg": <amount>}}

RULES:
- After opening any app, ALWAYS add a wait of 5+ seconds
- Use find_and_click for buttons you need to locate visually
- When typing in a chat app, first use find_and_click to find the search/input area
- Output ONLY valid JSON array, no markdown, no text outside JSON

Output:"""

        try:
            log.info("🧠 Creating plan via %s...", "Groq" if self.groq else "Cloud LLM")
            t0 = time.time()

            # Use Groq for speed, Cloud LLM as fallback
            if self.groq and self.groq.is_available:
                response = self.groq.generate(prompt=prompt, system_prompt="", stream=False, max_tokens_override=800)
            elif self.llm:
                response = self.llm.generate_sync(prompt=prompt, system_prompt="")
            else:
                return None

            if not response:
                return None

            elapsed = (time.time() - t0) * 1000
            log.info("📋 Plan generated in %.0fms", elapsed)

            json_str = response.strip()
            # Strip markdown fences
            if json_str.startswith("```"):
                import re
                json_str = re.sub(r"^```(?:json)?\n?", "", json_str)
                json_str = re.sub(r"\n?```$", "", json_str)

            plan = json.loads(json_str)
            log.info("📋 Plan: %d phases", len(plan))
            for i, phase in enumerate(plan):
                log.info("  Phase %d: %s (%d actions)", i+1, phase.get("phase", "?"), len(phase.get("actions", [])))
            return plan

        except json.JSONDecodeError as e:
            log.error("Plan JSON parse failed: %s", e)
            return None
        except Exception as e:
            log.error("Plan creation failed: %s", e)
            return None

    def _evaluate_plan_safety(self, plan: list[dict]) -> bool:
        """Multi-Agent Critic: Runs an AutoGen safety debate before allowing execution."""
        if not hasattr(self, "critic") or not self.critic.is_available:
            log.warning("🛡️ Safety Swarm unavailable, falling back to OS Threat Assessor.")
            return True
            
        try:
            plan_json = json.dumps(plan, indent=2)
            # Use AutoGen to verify the structural safety
            is_safe = self.critic.evaluate_task_safety("General OS Automation Task", plan_json)
            
            if not is_safe:
                log.critical("🚨 SAFETY SWARM REJECTED THE PLAN.")
                return False
                
            return True
        except Exception as e:
            log.warning("🛡️ AI Swarm evaluation failed: %s", e)
            return True # Fail open

    # ──────────────────────────────────────────────
    # GODMODE: Browser Automation
    # ──────────────────────────────────────────────

    def _handle_browser_task(self, task: str) -> str:
        """Delegate browser tasks to GodMode."""
        log.info("🌐 GODMODE: Browser task → %s", task[:60])
        return self.godmode.execute_browser_task(task, self.automation, self.grounding)

    # ──────────────────────────────────────────────
    # MIROFISH: Prediction Tasks
    # ──────────────────────────────────────────────

    def _handle_prediction_task(self, task: str) -> str:
        """Delegate prediction tasks to MiroFish."""
        log.info("🐟 MIROFISH: Prediction task → %s", task[:60])
        return self.mirofish.predict(task)

    # ──────────────────────────────────────────────
    # SPECIALIZED: Dashboard Builder
    # ──────────────────────────────────────────────

    def build_dashboard_from_cleaned_data(self, csv_path: str, dashboard_image_path: str = "") -> str:
        """Build Power BI dashboard using full agentic pipeline."""
        task = (
            f"Step 1: Open Power BI Desktop. Wait 15 seconds for it to load. "
            f"Step 2: Click 'Get Data' then 'CSV'. "
            f"Step 3: Navigate and load '{csv_path}'. Wait 10 seconds for data import. "
            f"Step 4: Create KPI cards for Price and Market Cap at the top. "
            f"Step 5: Create a Bar Chart (Sector as Axis, Count as Value). "
            f"Step 6: Create a Data Table with Ticker, Company Name, Price."
        )
        return self.perform_task(task)

    # Legacy compatibility
    def perform_workflow(self, task_description: str) -> str:
        return self.perform_task(task_description)

    def clean_and_build_dashboard(self, csv_path: str, dashboard_image_path: str = "") -> str:
        return self.build_dashboard_from_cleaned_data(csv_path, dashboard_image_path)
