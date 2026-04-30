"""
Pihu V2 — Interpreter Engine (The Safe Sandbox)
Replaces un-sandboxed OpenInterpreter with a secure Docker-bound REPL execution loop.
"""
from logger import get_logger
import re

log = get_logger("INTERPRETER")

class InterpreterEngine:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.sandbox = None
        self.is_available = False

        try:
            from sandbox.docker_executor import DockerExecutor
            self.sandbox = DockerExecutor(profile_name="python_sandbox")
            if self.sandbox.is_available:
                self.is_available = True
                log.info("💻 Secure Docker Sandbox Engine Initialized.")
            else:
                log.warning("Docker Sandbox failed to start. Docker SDK missing or daemon dead.")
        except Exception as e:
            log.error("Failed to initialize Docker Sandbox: %s", e)

    def _extract_python_code(self, llm_output: str) -> str:
        """Extracts code block from standard markdown triple backticks."""
        pattern = re.compile(r"```(?:python)?\n(.*?)\n```", re.DOTALL)
        match = pattern.search(llm_output)
        if match:
            return match.group(1).strip()
        
        # Fallback if no backticks but looks like raw code
        if "print(" in llm_output or "import " in llm_output:
            return llm_output.strip()
            
        return ""

    def execute_stream(self, prompt: str):
        """
        Executes an OS prompt securely by converting to Python and running via Docker.
        Yields human-readable updates.
        """
        if not self.is_available:
            yield "Mera Docker sandbox load nahi hua hai. Python code nahi chala sakti command line se."
            return

        if not self.llm_client:
            yield "Mujhe koi model nahi assign kiya gaya code likhne ke liye."
            return

        yield "Okay, main code likh ke sandbox mein run karti hoon. Ruko...\n"
        
        sys_prompt = (
            "You are Pihu, an AI executing code. You must write a Python 3.10 script to fulfill the user's prompt. "
            "Important logic constraints: "
            "1. You are running inside a containerized Linux Docker environment, NOT the host OS. "
            "2. Access is restricted exclusively to /workspace. "
            "3. You do not have network access. "
            "Return ONLY the raw python code wrapped in standard ```python ``` markdown. Do not provide explanations."
        )

        try:
            # 1. Ask LLM to generate the script
            # Use batch because we only want the final code block
            log.info("Generating sandbox script...")
            response = self.llm_client.generate(prompt=prompt, system_prompt=sys_prompt, stream=False)
            
            if not response:
                yield "Code generate karne mein LLM timeout ho gaya."
                return

            code = self._extract_python_code(response)
            if not code:
                yield "Main code samajh nahi paayi ya generate nahi hua theek se."
                return

            log.debug("Extracted Sandbox Code:\n%s", code)
            
            # 2. Run inside Docker Sandbox
            stdout, stderr, exit_code = self.sandbox.run_code(code)
            
            # 3. Analyze and Yield Results
            if exit_code == 0:
                log.info("Sandbox Execution successful.")
                result_msg = stdout if stdout else "Code executed silently without printing anything."
                
                # We do a quick LLM pass to summarize the output organically
                summary_prompt = f"The code executed successfully. Output:\n{result_msg}\nSummarize this very concisely in 1-2 friendly sentences to the user in Hinglish."
                final_summary = self.llm_client.generate(prompt=summary_prompt, stream=False)
                
                if final_summary:
                    yield final_summary
                else:
                    yield f"Run ho gaya! Ye lo output:\n{result_msg}"
            else:
                log.warning("Sandbox Execution failed. Exit code: %d", exit_code)
                yield "Code phat gaya container ke andar. Error details dhyan se padho:\n"
                yield stderr

        except Exception as e:
            log.error(f"Interpreter Engine Crushed: {e}")
            yield f"Execution pipeline fail ho gaya: {str(e)[:50]}"
