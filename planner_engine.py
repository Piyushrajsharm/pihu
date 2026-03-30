"""
Pihu V2 — Planner Engine (The Architect)
Integrates Microsoft TaskWeaver to decompose complex user goals into structured plans.
"""
import os
import sys
from pathlib import Path
from logger import get_logger

log = get_logger("PLANNER")

class PlannerEngine:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.is_available = True
        self.app = None
        self._init_taskweaver()

    def _init_taskweaver(self):
        try:
            # 1. Add TaskWeaver to sys.path
            tw_root = str(Path(__file__).parent / "third_party" / "taskweaver")
            if tw_root not in sys.path:
                sys.path.append(tw_root)
                
            from taskweaver.app.app import TaskWeaverApp
            
            # 2. Instantiate the App (using the config we wrote)
            # Root dir for config and plugins
            app_dir = str(Path(__file__).parent / "third_party" / "taskweaver" / "project")
            self.app = TaskWeaverApp(app_dir=app_dir)
            log.info("📐 V2 Architect: TaskWeaver Planner Initialized.")
        except ImportError:
            log.warning("TaskWeaver dependencies not found. Run Phase 1 setup again.")
            self.is_available = False
        except Exception as e:
            log.error("TaskWeaver instantiation failed: %s", e)
            self.is_available = False

    def plan_task(self, query: str):
        """
        Sends a query to TaskWeaver and returns the structured decomposition.
        Yields the 'Plan' chunks to the user before execution.
        """
        if not self.is_available or not self.app:
            yield "Planning engine unavailable. Using linear execution."
            return

        try:
            # 3. Start a stateful session
            session = self.app.get_session()
            
            # Simple wrapper to extract the message
            response = session.send_message(query)
            
            # TaskWeaver returns a Response object
            if response and response.message:
                yield f"[PLANNER]: {response.message}"
            else:
                yield "Problem complex hai, par plan clear nahi hua. Linear mode try karti hoon."
                
        except Exception as e:
            log.error("Planning failed: %s", e)
            yield f"Planning me error aa gaya: {e}"
