"""
Pihu — Secret Broker
Wraps the DPAPI Vault to provide scoped, strictly controlled access to raw secrets.
Prevents arbitrary tools from extracting API keys they don't need.
"""
from dataclasses import dataclass
from typing import Optional, Dict, List
import uuid

from logger import get_logger
from security.security_core import Vault
from security.policy_engine import ActionType

log = get_logger("SECRET-BROKER")

@dataclass
class SecretRef:
    key_name: str
    opaque_id: str

class SecretBroker:
    """
    Manages secret retrieval based on the tool's access profile.
    Registers all secrets with SecretRedactor on boot.
    """
    
    def __init__(self, vault: Vault, policy_engine):
        self._vault = vault
        self._policy = policy_engine
        
        # Opaque mapping: id -> key_name
        self._refs: Dict[str, str] = {}
        
        self._register_with_redactor()

    def _register_with_redactor(self):
        """Pre-emptively load all secrets into the Redactor to ensure they never leak."""
        from security.secret_redactor import SecretRedactor
        redactor = SecretRedactor()
        
        # Register keys to scrub list_keys() output if it ever leaks
        for k in self._vault.list_keys():
            redactor.add_known_secret(k)
            
            # Decrypt and register values
            val = self._vault.retrieve(k)
            if val:
                redactor.add_known_secret(val)
                
        log.info("🛡️ SecretBroker registered %d secrets with global redactor.", len(self._vault.list_keys()))

    def get_ref(self, key_name: str) -> Optional[SecretRef]:
        """Returns an opaque reference, not the secret itself."""
        if self._vault.retrieve(key_name) is None:
            return None
            
        opaque = str(uuid.uuid4())
        self._refs[opaque] = key_name
        return SecretRef(key_name=key_name, opaque_id=opaque)

    def retrieve_raw(self, key_name: str, action: ActionType) -> Optional[str]:
        """
        Retrieves the raw secret string ONLY IF the current tool/action is authorized.
        """
        # 1. Look up profile for this action
        profile = self._policy._find_tool_profile(action)
        if not profile:
            log.warning("Secret request denied: No tool profile found for action %s", action.value)
            return None
            
        # 2. Check if profile authorizes this secret
        authorized_secrets = profile.get("allowed_secrets", [])
        if "*" not in authorized_secrets and key_name not in authorized_secrets:
            log.warning("Secret request denied: Tool profile '%s' is not authorized to access secret '%s'", action.value, key_name)
            return None
            
        # 3. Return raw value
        log.debug("SecretBroker granted '%s' access to '%s'", action.value, key_name)
        return self._vault.retrieve(key_name)

    def store(self, key_name: str, value: str):
        self._vault.store(key_name, value)
        # Update redactor
        from security.secret_redactor import SecretRedactor
        redactor = SecretRedactor()
        redactor.add_known_secret(value)
        redactor.add_known_secret(key_name)

    def list_keys(self) -> List[str]:
        return self._vault.list_keys()
