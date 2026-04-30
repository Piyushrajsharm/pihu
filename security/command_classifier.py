"""
Pihu — Command Classifier
Tokenizes, classifies, and risk-scores shell commands before execution.

This replaces the simplistic string-pattern ThreatAssessor with
structured analysis: metacharacter detection, privilege escalation detection,
package install detection, persistence detection, and blast radius estimation.

This module is DETERMINISTIC. The LLM never touches it.
"""

import re
import shlex
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional

from logger import get_logger

log = get_logger("CMD-CLASS")


class CommandRisk(IntEnum):
    """Risk levels for classified commands."""
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    BLOCKED = 5


@dataclass
class CommandAssessment:
    """Structured assessment of a shell command."""
    original: str
    executable: str
    arguments: list[str]
    risk: CommandRisk
    risk_label: str
    flags: list[str]
    explanation: str
    blocked: bool
    requires_approval: bool
    requires_sandbox: bool
    suggested_action: str  # "allow", "deny", "sandbox", "approval", "dry_run"


# ──────────────────────────────────────────────
# DETECTION PATTERNS
# ──────────────────────────────────────────────

# Shell metacharacters that enable chaining/redirection
METACHARACTER_PATTERNS = [
    (r"&&", "command chaining (&&)"),
    (r"\|\|", "conditional chaining (||)"),
    (r"(?<!\|)\|(?!\|)", "pipe (|)"),
    (r";", "command separator (;)"),
    (r">>", "append redirect (>>)"),
    (r"(?<!>)>(?!>)", "output redirect (>)"),
    (r"<", "input redirect (<)"),
    (r"`[^`]+`", "backtick command substitution"),
    (r"\$\(", "command substitution $()"),
    (r"\$\{", "variable expansion ${}")
]

# Privilege escalation commands
PRIVILEGE_ESCALATION = {
    "sudo", "su", "runas", "doas", "pkexec",
    "net user", "net localgroup", "net group",
    "reg add", "reg delete", "regedit",
    "schtasks", "sc create", "sc config", "sc delete",
    "bcdedit", "diskpart",
    "icacls", "takeown", "cacls",
    "chmod +s", "chown root",
    "setenforce", "getenforce",
    "visudo",
}

# Package installation commands (can install arbitrary code)
PACKAGE_INSTALL = {
    "pip install", "pip3 install",
    "npm install", "npm i ", "npx ",
    "yarn add", "yarn global",
    "cargo install",
    "go install", "go get",
    "gem install",
    "choco install", "scoop install", "winget install",
    "apt install", "apt-get install",
    "yum install", "dnf install",
    "pacman -S", "brew install",
    "snap install", "flatpak install",
}

# Startup persistence mechanisms
PERSISTENCE_PATTERNS = [
    r"Start\s*Menu.*Startup",
    r"HKCU.*\\Run",
    r"HKLM.*\\Run",
    r"HKCU.*\\RunOnce",
    r"schtasks\s+/create",
    r"crontab\s+-e",
    r"crontab\s+-l",
    r"systemctl\s+enable",
    r"launchctl\s+load",
    r"\.bashrc",
    r"\.bash_profile",
    r"\.zshrc",
    r"\.profile",
    r"autoexec\.bat",
]

# Destructive commands — hard block
DESTRUCTIVE_COMMANDS = {
    "rm -rf /", "rm -rf /*", "rm -rf ~",
    "del /s /q c:", "del /s /q d:",
    "format c:", "format d:",
    "diskpart", "mkfs",
    "dd if=/dev/zero", "dd if=/dev/urandom",
    "shred", "wipe",
    "shutdown", "restart",
    "halt", "poweroff", "init 0",
    ":(){ :|:& };:",  # Fork bomb
    "drop database", "drop table",
    "truncate table",
}

# Reconnaissance commands — generally safe but worth noting
RECON_COMMANDS = {
    "whoami", "hostname", "uname", "id",
    "systeminfo", "ipconfig", "ifconfig",
    "netstat", "ss", "arp", "route",
    "tasklist", "ps", "top",
    "dir", "ls", "cat", "type",
    "echo", "pwd", "printenv", "env",
    "git status", "git log", "git diff", "git branch",
}

# Safe commands — auto-allow
SAFE_COMMANDS = {
    "echo", "pwd", "date", "time", "cal",
    "head", "tail", "wc", "sort", "uniq",
    "grep", "find", "which", "where",
    "python --version", "python3 --version",
    "node --version", "npm --version",
    "git status", "git log", "git diff",
    "dir", "ls", "cat", "type", "more", "less",
}


class CommandClassifier:
    """Structured shell command analyzer."""

    def classify(self, command: str) -> CommandAssessment:
        """Tokenize and classify a shell command."""
        cmd_stripped = command.strip()
        cmd_lower = cmd_stripped.lower()
        
        flags = []
        risk = CommandRisk.SAFE
        blocked = False
        requires_approval = False
        requires_sandbox = False
        
        # 1. Tokenize
        executable, arguments = self._tokenize(cmd_stripped)
        
        # 2. Check hard-blocked destructive commands
        for destructive in DESTRUCTIVE_COMMANDS:
            if destructive in cmd_lower:
                flags.append(f"DESTRUCTIVE: matches '{destructive}'")
                risk = CommandRisk.BLOCKED
                blocked = True
        
        # 3. Check metacharacters (DO THIS BEFORE SAFE COMMANDS)
        if not blocked:
            for pattern, description in METACHARACTER_PATTERNS:
                if re.search(pattern, cmd_stripped):
                    flags.append(f"METACHAR: {description}")
                    risk = max(risk, CommandRisk.HIGH)
                    requires_approval = True

        # 4. Check safe commands (fast path) ONLY IF NO METACHARS
        if not blocked and risk < CommandRisk.HIGH:
            for safe in SAFE_COMMANDS:
                if cmd_lower.startswith(safe):
                    flags.append(f"SAFE: recognized command '{safe}'")
                    return CommandAssessment(
                        original=cmd_stripped,
                        executable=executable,
                        arguments=arguments,
                        risk=CommandRisk.SAFE,
                        risk_label="SAFE",
                        flags=flags,
                        explanation=f"Recognized safe command: '{executable}'",
                        blocked=False,
                        requires_approval=False,
                        requires_sandbox=False,
                        suggested_action="allow",
                    )

        
        # 5. Check privilege escalation
        if not blocked:
            for priv_cmd in PRIVILEGE_ESCALATION:
                if priv_cmd in cmd_lower:
                    flags.append(f"PRIV_ESC: '{priv_cmd}'")
                    risk = max(risk, CommandRisk.CRITICAL)
                    blocked = True
        
        # 6. Check package installation
        if not blocked:
            for pkg_cmd in PACKAGE_INSTALL:
                if pkg_cmd in cmd_lower:
                    flags.append(f"PKG_INSTALL: '{pkg_cmd}'")
                    risk = max(risk, CommandRisk.HIGH)
                    requires_approval = True
        
        # 7. Check persistence mechanisms
        if not blocked:
            for persist_pattern in PERSISTENCE_PATTERNS:
                if re.search(persist_pattern, cmd_stripped, re.IGNORECASE):
                    flags.append(f"PERSISTENCE: matches '{persist_pattern}'")
                    risk = max(risk, CommandRisk.CRITICAL)
                    blocked = True
        
        # 8. Check recon commands
        if not blocked and risk == CommandRisk.SAFE:
            for recon in RECON_COMMANDS:
                if cmd_lower.startswith(recon):
                    flags.append(f"RECON: '{recon}'")
                    risk = CommandRisk.LOW
        
        # 9. Network-accessing commands
        if not blocked:
            network_indicators = [
                "curl ", "wget ", "invoke-webrequest",
                "http://", "https://", "ftp://",
                "ssh ", "scp ", "rsync ",
                "nslookup ", "dig ", "nmap ",
            ]
            for net_cmd in network_indicators:
                if net_cmd in cmd_lower:
                    flags.append(f"NETWORK: '{net_cmd.strip()}'")
                    risk = max(risk, CommandRisk.MEDIUM)
                    requires_approval = True
        
        # 10. If nothing flagged but command is unrecognized, require sandbox
        if not blocked and risk == CommandRisk.SAFE and executable not in {
            c.split()[0] for c in SAFE_COMMANDS
        }:
            risk = CommandRisk.MEDIUM
            requires_sandbox = True
            flags.append("UNKNOWN: unrecognized command, routing to sandbox")
        
        # Calculate suggested action
        if blocked:
            suggested = "deny"
        elif requires_approval:
            suggested = "approval"
        elif requires_sandbox:
            suggested = "sandbox"
        elif risk <= CommandRisk.LOW:
            suggested = "allow"
        else:
            suggested = "approval"
        
        explanation = self._build_explanation(executable, flags, risk)
        
        return CommandAssessment(
            original=cmd_stripped,
            executable=executable,
            arguments=arguments,
            risk=risk,
            risk_label=CommandRisk(risk).name,
            flags=flags,
            explanation=explanation,
            blocked=blocked,
            requires_approval=requires_approval,
            requires_sandbox=requires_sandbox,
            suggested_action=suggested,
        )

    @staticmethod
    def _tokenize(command: str) -> tuple[str, list[str]]:
        """Split command into executable and arguments."""
        try:
            tokens = shlex.split(command, posix=(os.name != "nt"))
            if tokens:
                return tokens[0], tokens[1:]
            return "", []
        except ValueError:
            # shlex failed (unbalanced quotes etc)
            parts = command.split()
            if parts:
                return parts[0], parts[1:]
            return command, []

    @staticmethod
    def _build_explanation(executable: str, flags: list[str], risk: CommandRisk) -> str:
        """Build plain-language explanation for the user."""
        if not flags:
            return f"Command '{executable}' has no detected risk factors."
        
        risk_names = {
            CommandRisk.SAFE: "safe",
            CommandRisk.LOW: "low-risk",
            CommandRisk.MEDIUM: "medium-risk", 
            CommandRisk.HIGH: "high-risk",
            CommandRisk.CRITICAL: "critical-risk",
            CommandRisk.BLOCKED: "BLOCKED",
        }
        
        parts = [f"Command '{executable}' classified as {risk_names.get(risk, 'unknown')}."]
        parts.append("Detected factors:")
        for flag in flags:
            parts.append(f"  • {flag}")
        
        return "\n".join(parts)


# Needed for shlex on Windows
import os
