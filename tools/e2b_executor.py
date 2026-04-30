"""
Pihu — E2B Code Interpreter Tool
Secure, ephemeral cloud sandbox for Python execution.
Supports persistent sessions and variable state across turns.
"""

import os
from typing import Optional, Dict, Any

from logger import get_logger

log = get_logger("TOOL")

class E2BExecutor:
    """Secure Python execution environment using E2B.
    
    Provides a sandboxed Jupyter-like environment for Pihu to perform
    computational tasks, data analysis, and advanced logic.
    """
    
    _instance: Optional['E2BExecutor'] = None
    _lock = None # threading.Lock() if thread safety needed

    def __init__(self, api_key: Optional[str] = None):
        from config import E2B_API_KEY
        
        # 1. API Key Precedence: Argument -> Environment -> Vault (Future)
        self.api_key = api_key or E2B_API_KEY
        
        if not self.api_key:
            # Try to fetch from Pihu Vault
            try:
                from security.security_core import SecurityManager
                sec = SecurityManager()
                from security.policy_engine import ActionType
                self.api_key = sec.secret_broker.retrieve_raw("E2B_API_KEY", ActionType.TOOL_EXEC)
            except Exception:
                pass

        self._sandbox = None
        self.session_id: Optional[str] = None
        
        if self.api_key:
            log.info("E2BExecutor initialized (API Key detected)")
        else:
            log.warning("E2BExecutor: Missing E2B_API_KEY. Sandbox will fail to start.")

    def _ensure_sandbox(self):
        """Lazy initialization of the E2B Sandbox."""
        if self._sandbox:
            return True
            
        if not self.api_key:
            return False

        try:
            from e2b_code_interpreter import CodeInterpreter
            log.info("🚀 Starting new E2B Code Interpreter sandbox...")
            self._sandbox = CodeInterpreter(api_key=self.api_key)
            log.info("✅ E2B Sandbox started: %s", self._sandbox.sandbox_id)
            return True
        except Exception as e:
            log.error("Failed to start E2B Sandbox: %s", e)
            return False

    def execute_python(self, code: str) -> Dict[str, Any]:
        """Execute Python code in the sandbox and return the results."""
        if not self._ensure_sandbox():
            return {
                "success": False, 
                "stdout": "", 
                "stderr": "E2B Sandbox not started. Please run `python scripts/setup_e2b.py` to set your API key.",
                "error": "ConfigurationError"
            }

        try:
            # Use notebook.exec_cell for Jupyter-like behavior (returns data, plots, etc)
            execution = self._sandbox.notebook.exec_cell(code)
            
            result = {
                "success": not execution.error,
                "stdout": execution.logs.stdout,
                "stderr": execution.logs.stderr,
                "error": None
            }
            
            if execution.error:
                result["error"] = {
                    "name": execution.error.name,
                    "value": execution.error.value,
                    "traceback": execution.error.traceback
                }
            
            # Extract data results (e.g. from the last line of the cell)
            if execution.results:
                # Get the first result's text or data
                res = execution.results[0]
                result["results"] = str(res)
            
            log.info("📊 E2B Execution Complete | Success: %s", result["success"])
            return result

        except Exception as e:
            log.error("E2B Execution error: %s", e)
            return {"success": False, "stdout": "", "stderr": str(e), "error": "InternalError"}

    def stop(self):
        """Close the sandbox session."""
        if self._sandbox:
            try:
                self._sandbox.close()
                log.info("🔌 E2B Sandbox closed.")
            except Exception as e:
                log.error("Error closing E2B Sandbox: %s", e)
            self._sandbox = None

# Global singleton or factory
_global_executor = None

def get_e2b_executor() -> E2BExecutor:
    global _global_executor
    if _global_executor is None:
        _global_executor = E2BExecutor()
    return _global_executor
