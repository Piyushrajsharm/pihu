"""
Pihu SaaS — E2B Ephemeral Cloud Sandbox
Creates an isolated V8/Linux container per tenant execute system commands, python code, and node.js, completely isolating Pihu from the actual API server.
"""

import os
import re
from typing import Generator
from logger import get_logger

log = get_logger("CLOUD_SANDBOX")

class CloudSandboxExecutor:
    """Manages ephemeral VM Sandboxes via E2B."""
    
    def __init__(self, tenant_id: str):
        from e2b_code_interpreter import Sandbox
        self.tenant_id = tenant_id
        self.sandbox_cls = Sandbox
        self.api_key = os.getenv("E2B_API_KEY")

        if not self.api_key:
            log.warning("E2B_API_KEY not found. Sandbox will run in Mock Mode.")

    def run_code_stream(self, python_code: str) -> Generator[str, None, None]:
        """Runs Python code securely and streams stdout/stderr."""
        if not self.api_key:
            yield f"[MOCK E2B SANDBOX ({self.tenant_id})] Executing:\n{python_code}\n\n[MOCK E2B] Done."
            return

        try:
            yield "Spinning up secure Cloud E2B Sandbox...\n"
            # Creates an ephemeral VM. Lifecycle is bound to the 'with' context.
            with self.sandbox_cls(api_key=self.api_key) as sandbox:
                yield "Sandbox booted. Running payload...\n\n"
                
                # Execute the code in the sandbox
                execution = sandbox.run_code(python_code)
                
                # Stream logs back to the user
                if execution.logs.stdout:
                    for line in execution.logs.stdout:
                        yield f"{line}\n"
                        
                if execution.logs.stderr:
                    for line in execution.logs.stderr:
                        yield f"[ERR] {line}\n"
                        
                if execution.error:
                    yield f"\n[RUNTIME EXCEPTION] {execution.error.name}: {execution.error.value}\n"
                    
                yield "\n--- Execution Complete. Sandbox Destroyed. ---"

        except Exception as e:
            log.error("Cloud Sandbox Error: %s", e)
            yield f"CRITICAL: Failed to execute payload in Sandbox: {e}"

    def extract_and_run(self, intent_payload: str) -> Generator[str, None, None]:
        """Helper to extract ```python blocks from intent and run them."""
        python_blocks = re.findall(r'```(?:python|py)\s*\n(.*?)\n```', intent_payload, re.DOTALL | re.IGNORECASE)
        if not python_blocks:
            yield "No executable Python block was provided. Refusing to run raw natural-language input."
            return
            
        code_to_run = "\n".join(python_blocks)
        yield from self.run_code_stream(code_to_run)
