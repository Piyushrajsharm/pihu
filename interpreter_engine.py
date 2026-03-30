"""
Pihu V2 — Interpreter Engine (The Hands)
Replaces raw OS commands with OpenInterpreter's Sandboxed Python execution loop.
Filters output traces dynamically so Voice models exclusively speak organic text.
"""
from logger import get_logger
import os

log = get_logger("INTERPRETER")

class InterpreterEngine:
    def __init__(self):
        try:
            from interpreter import interpreter
            
            # --- V2 Architecture Constraints: 100% Offline via Ollama ---
            interpreter.offline = True
            interpreter.llm.model = "ollama/qwen2.5:3b"
            interpreter.llm.api_base = "http://localhost:11434"
            interpreter.auto_run = True # Pihu is autonomous. Force bypass of [y/n] confirms.
            interpreter.llm.temperature = 0.0
            
            # Persona consistency: inject epistemic humility into the base interpreter logic
            interpreter.system_message += """\nUnderstand you are executing as Pihu's underlying engine. Keep your conversational output in extremely concise Hinglish, exactly 1-2 sentences. If your code fails 3 times, gracefully surrender by stopping execution."""

            self.interpreter = interpreter
            self.is_available = True
            log.info("💻 V2 Hands: OpenInterpreter Sandboxed Engine Initialized.")
        except ImportError:
            log.warning("OpenInterpreter missing. Falling back to legacy OpenClaw. Run `pip install open-interpreter`")
            self.is_available = False
            self.interpreter = None

    def execute_stream(self, prompt: str):
        """
        Executes an OS prompt autonomously through OpenInterpreter's self-correcting logic loop.
        Generator Stream Filter: Intercepts `type: code` so Kokoro TTS only reads human-readable intent.
        """
        if not self.is_available:
            yield "Yahan execution environment available nahi hai. Installer check karna padega."
            return

        try:
            yield "Okay ruko, script chalati hoon... "
            
            # Stream=True yields chunks:
            # {'role': 'assistant', 'type': 'message', 'content': 'I will do X'}
            # {'role': 'assistant', 'type': 'code', 'format': 'python', 'content': 'print()'}
            generator = self.interpreter.chat(prompt, stream=True, display=False)
            
            for chunk in generator:
                if isinstance(chunk, dict):
                    # Only yield pure conversational output
                    if chunk.get("type") == "message" and "content" in chunk:
                        text = chunk["content"]
                        # Strip terminal-style markdown just in case
                        if "`" not in text: 
                            yield text

                    # Logging internal code for telemetry but excluding from Voice stream
                    elif chunk.get("type") == "code" and "content" in chunk:
                        log.debug(f"[Interpreter Code]: {chunk['content'][:50]}...")
                        
        except Exception as e:
            log.error(f"Interpreter Execution Crushed: {e}")
            yield f"Execution buri tarah phat chuka hai: {str(e)[:50]}"
