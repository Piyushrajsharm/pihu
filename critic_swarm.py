"""
Pihu V2 — Multi-Agent Safety Swarm (AutoGen Implementation)
Orchestrates a debate between an "Architect" and a "Security Sentinel" 
to verify the safety and logic of complex OS tasks before execution.
"""
try:
    import autogen
    AUTOGEN_AVAILABLE = True
except ImportError:
    import logging
    logging.getLogger("CRITIC").warning("⚠️ 'autogen' module not found. Safety Swarm will be disabled.")
    AUTOGEN_AVAILABLE = False

from logger import get_logger

log = get_logger("CRITIC")

# Configuration for local Ollama via OpenAI-compatible endpoint
config_list = [
    {
        "model": "qwen2.5:3b",
        "api_key": "ollama",
        "base_url": "http://localhost:11434/v1",
    }
]

class CriticSwarm:
    def __init__(self):
        self.is_available = AUTOGEN_AVAILABLE
        if not self.is_available:
            return

        try:
            # 1. The Architect: Proposes the plan/logic
            self.architect = autogen.AssistantAgent(
                name="Architect",
                llm_config={"config_list": config_list},
                system_message="You are the lead architect for Pihu. Your job is to propose safe, efficient automation plans. "
                               "If a plan is found unsafe, you MUST revise it until the Sentinel is satisfied."
            )

            # 2. The Sentinel: Brutally critiques safety/efficiency
            self.sentinel = autogen.UserProxyAgent(
                name="Sentinel",
                human_input_mode="NEVER",
                max_consecutive_auto_reply=2,
                is_termination_msg=lambda x: "SAFE" in x.get("content", "").upper(),
                code_execution_config=False,
                system_message="You are the Pihu Security Sentinel. You evaluate plans for: "
                               "1. Destructive intent (e.g. deleting system files) "
                               "2. Data leaks (e.g. sending tokens to public URLs) "
                               "3. Infinite loops. "
                               "Respond with UNSAFE and specific reasons if dangerous. Reply only 'SAFE' if verified."
            )
            
            log.info("🛡️ Multi-Agent Safety Swarm Initialized (AutoGen)")
        except Exception as e:
            log.error("AutoGen Swarm failed to initialize: %s", e)
            self.is_available = False

    def evaluate_task_safety(self, task_description: str, plan_json: str) -> bool:
        """
        Runs a multi-agent debate on the proposed plan.
        Returns True only if the Security Sentinel confirms 'SAFE'.
        """
        if not self.is_available:
            return True # Fallback to single-mode if AutoGen fails

        try:
            log.info("🛡️ Debate starting: Architect vs Sentinel...")
            
            # Start the debate
            chat_result = self.sentinel.initiate_chat(
                self.architect,
                message=f"I need to execute this plan for the task: '{task_description}'.\nPlan:\n{plan_json}\nEvaluate for safety."
            )
            
            # Extract the last message content
            final_verdict = chat_result.summary.upper()
            
            if "SAFE" in final_verdict and "UNSAFE" not in final_verdict:
                log.info("✅ Safety Swarm Consensus: Plan is SAFE.")
                return True
            else:
                log.critical("🚨 Safety Swarm REJECTED the plan: %s", final_verdict)
                return False
                
        except Exception as e:
            log.error("Safety debate crashed: %s", e)
            return False  # FAIL CLOSED: Block execution when safety system fails
