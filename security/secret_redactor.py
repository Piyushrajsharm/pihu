"""
Pihu — Secret Redactor
Scans strings for patterns matching API keys, tokens, passwords,
connection strings, and private keys. Replaces them with [REDACTED].

This is used in ALL output paths: audit logs, console, error messages,
memory storage, and LLM prompt injection defense.
"""

import re
from typing import Optional

from logger import get_logger

log = get_logger("REDACTOR")


# ──────────────────────────────────────────────
# REDACTION PATTERNS
# ──────────────────────────────────────────────

# Each tuple: (pattern_name, compiled_regex)
_PATTERNS: list[tuple[str, re.Pattern]] = []


def _register(name: str, pattern: str, flags: int = 0):
    """Register a redaction pattern."""
    _PATTERNS.append((name, re.compile(pattern, flags)))


# API Keys (generic long alphanumeric strings preceded by key-like context)
_register("api_key_assignment",
          r'(?i)(api[_-]?key|apikey|api[_-]?secret|access[_-]?key|secret[_-]?key)\s*[:=]\s*["\']?([A-Za-z0-9_\-]{20,})["\']?')

# Bearer tokens
_register("bearer_token",
          r'(?i)(Bearer\s+)([A-Za-z0-9_\-\.]{20,})')

# JWT tokens (three base64 segments separated by dots)
_register("jwt_token",
          r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}')

# NVIDIA NIM pattern
_register("nvidia_key",
          r'nvapi-[A-Za-z0-9_\-]{20,}')

# OpenAI-style keys
_register("openai_key",
          r'sk-[A-Za-z0-9]{20,}')

# AWS keys
_register("aws_access_key",
          r'(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}')
_register("aws_secret_key",
          r'(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[:=]\s*["\']?([A-Za-z0-9/+=]{40})["\']?')

# GitHub tokens
_register("github_token",
          r'gh[pousr]_[A-Za-z0-9_]{36,}')

# Google API keys
_register("google_api_key",
          r'AIza[A-Za-z0-9_\-]{35}')

# Stripe keys
_register("stripe_key",
          r'(?:sk|pk|rk)_(?:test|live)_[A-Za-z0-9]{20,}')

# Generic password in connection strings
_register("connection_string_password",
          r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?([^\s"\';&]{8,})["\']?')

# Database URLs with credentials
_register("db_url_credentials",
          r'(?i)(postgres|mysql|mongodb|redis|amqp)(?:ql)?://[^:]+:([^@]+)@')

# Private keys
_register("private_key_block",
          r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
          re.MULTILINE)

# SSH private key material
_register("ssh_key_material",
          r'-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----[\s\S]*?-----END\s+OPENSSH\s+PRIVATE\s+KEY-----',
          re.MULTILINE)

# Generic hex secrets (32+ hex chars often = hashes/keys)
_register("hex_secret_in_config",
          r'(?i)(secret|token|key|password|credential)\s*[:=]\s*["\']?([0-9a-f]{32,})["\']?')

# Environment variable assignments with sensitive names
_register("env_var_secret",
          r'(?i)(?:export\s+)?((?:API|SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL|AUTH)[A-Z_]*)\s*=\s*["\']?([^\s"\']{8,})["\']?')

REDACTED = "[REDACTED]"


class SecretRedactor:
    """Scans and redacts secrets from arbitrary text."""

    def __init__(self, extra_secrets: list[str] = None):
        """
        Args:
            extra_secrets: Additional literal strings to redact (e.g., known API keys from vault).
        """
        self._literal_secrets: list[str] = []
        if extra_secrets:
            # Sort by length descending so longer secrets match first
            self._literal_secrets = sorted(extra_secrets, key=len, reverse=True)

    def add_known_secret(self, secret: str):
        """Register an additional literal secret to always redact."""
        if secret and len(secret) >= 8:
            self._literal_secrets.append(secret)
            # Re-sort
            self._literal_secrets.sort(key=len, reverse=True)

    def redact(self, text: str) -> str:
        """Scan text and replace all detected secrets with [REDACTED]."""
        if not text:
            return text
        
        result = text
        
        # 1. Redact known literal secrets first (exact match)
        for secret in self._literal_secrets:
            if secret in result:
                result = result.replace(secret, REDACTED)
        
        # 2. Apply regex patterns
        for pattern_name, pattern in _PATTERNS:
            # For patterns with capture groups, we redact the captured group
            # For patterns without, we redact the entire match
            if pattern.groups > 0:
                def _replacer(m):
                    groups = m.groups()
                    if len(groups) >= 2:
                        # Keep the label, redact the value
                        return m.group(0).replace(groups[-1], REDACTED)
                    return REDACTED
                result = pattern.sub(_replacer, result)
            else:
                result = pattern.sub(REDACTED, result)
        
        return result

    def contains_secrets(self, text: str) -> bool:
        """Quick check if text contains any detectable secrets."""
        if not text:
            return False
        
        for secret in self._literal_secrets:
            if secret in text:
                return True
        
        for _, pattern in _PATTERNS:
            if pattern.search(text):
                return True
        
        return False

    def scan(self, text: str) -> list[dict]:
        """Return a list of detected secrets with their types and locations."""
        findings = []
        
        for secret in self._literal_secrets:
            idx = text.find(secret)
            if idx >= 0:
                findings.append({
                    "type": "known_literal",
                    "position": idx,
                    "length": len(secret),
                })
        
        for pattern_name, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                findings.append({
                    "type": pattern_name,
                    "position": match.start(),
                    "length": match.end() - match.start(),
                })
        
        return findings


# Global singleton
secret_redactor = SecretRedactor()
