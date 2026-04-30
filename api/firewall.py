"""
Pihu SaaS — Zero-Trust Semantic Firewall
Inspects incoming REST and WebSocket prompts for adversarial jailbreaks or system prompt injections.
"""

import re
from fastapi import HTTPException
from logger import get_logger

log = get_logger("AI_FIREWALL")

# High-risk adversarial keywords typically used in prompt injection
JAILBREAK_PATTERNS = [
    r"(?i)ignore all previous instructions",
    r"(?i)you are now [a-z]+",
    r"(?i)disregard your persona",
    r"(?i)bypass restrictions",
    r"(?i)system override",
    r"(?i)print your system prompt"
]

class PromptFirewall:
    def inspect(self, prompt: str):
        """
        Runs heuristic pattern matching on the prompt.
        In a 50B+ API SaaS, this function would offload to Cloudflare AI Gateway or LlamaGuard.
        """
        for pattern in JAILBREAK_PATTERNS:
            if re.search(pattern, prompt):
                log.warning(f"SECURITY ALERT: Jailbreak attempt blocked via signature match: {pattern}")
                raise HTTPException(
                    status_code=403, 
                    detail="Forbidden: Suspected prompt injection or jailbreak attempt detected."
                )

firewall = PromptFirewall()
