"""
Pihu — Filesystem Guard
Path normalization, workspace boundary enforcement, protected path list,
symlink resolution, and file type risk classification.

This module is DETERMINISTIC. The LLM never touches it.
"""

import os
import re
import fnmatch
from enum import Enum
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from logger import get_logger

log = get_logger("FS-GUARD")


class FileOperation(Enum):
    """Classified filesystem operation types."""
    READ = "read"
    CREATE = "create"
    MODIFY = "modify"
    RENAME = "rename"
    DELETE = "delete"
    RECURSIVE_DELETE = "recursive_delete"
    EXECUTE = "execute"
    LIST = "list"


class FileRiskLevel(Enum):
    """Risk classification for file types."""
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


@dataclass
class PathAssessment:
    """Result of filesystem guard evaluation."""
    normalized_path: str
    is_in_workspace: bool
    is_protected: bool
    file_risk: FileRiskLevel
    operation: FileOperation
    reasons: list[str]
    allowed: bool
    requires_approval: bool


# ──────────────────────────────────────────────
# PROTECTED PATHS — OS-critical locations
# ──────────────────────────────────────────────

PROTECTED_PATH_PATTERNS_WINDOWS = [
    "C:/Windows/**",
    "C:/Program Files/**",
    "C:/Program Files (x86)/**",
    "C:/ProgramData/**",
    "**/System32/**",
    "**/SysWOW64/**",
    # User-critical directories
    "**/AppData/Local/Microsoft/**",
    "**/AppData/Roaming/Microsoft/**",
    # SSH and credential stores
    "**/.ssh/**",
    "**/.gnupg/**",
    "**/.aws/**",
    "**/.azure/**",
    "**/.gcloud/**",
    "**/.config/gcloud/**",
    # Browser profile directories
    "**/AppData/Local/Google/Chrome/**",
    "**/AppData/Local/Microsoft/Edge/**",
    "**/AppData/Roaming/Mozilla/Firefox/**",
    # Package managers
    "**/AppData/Roaming/npm/**",
    "**/AppData/Local/pip/**",
    # Shell configuration
    "**/.bashrc",
    "**/.bash_profile",
    "**/.zshrc",
    "**/.profile",
    "**/Documents/PowerShell/**",
    "**/Documents/WindowsPowerShell/**",
    # Registry hives (if accessed as files)
    "**/NTUSER.DAT",
    "**/UsrClass.dat",
    # Startup directories
    "**/Start Menu/Programs/Startup/**",
    "**/AppData/Roaming/Microsoft/Windows/Start Menu/**",
    # Credential stores
    "**/Credentials/**",
    "**/Vault/**",
    # Git config (global)
    "**/.gitconfig",
]

PROTECTED_PATH_PATTERNS_LINUX = [
    "/etc/**",
    "/usr/**",
    "/bin/**",
    "/sbin/**",
    "/boot/**",
    "/proc/**",
    "/sys/**",
    "/dev/**",
    "/root/**",
    "**/.ssh/**",
    "**/.gnupg/**",
    "**/.bashrc",
    "**/.bash_profile",
    "**/.zshrc",
    "**/.profile",
    "/var/log/**",
    "/var/spool/cron/**",
    "**/crontab",
]

# ──────────────────────────────────────────────
# DANGEROUS FILE EXTENSIONS
# ──────────────────────────────────────────────

BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".sys", ".drv", ".scr", ".com", ".ocx",
    ".reg",  # Windows registry
    ".msi", ".msp",  # Installers
    ".vbs", ".vbe", ".wsf", ".wsh",  # Windows scripting
    ".inf",  # Setup information
    ".lnk",  # Shortcuts (can be weaponized)
}

DANGEROUS_EXTENSIONS = {
    ".bat", ".cmd",  # Windows batch
    ".ps1", ".psm1", ".psd1",  # PowerShell
    ".sh", ".bash", ".zsh",  # Shell scripts
    ".py",  # Only dangerous when EXECUTING, not reading/writing
    ".js", ".mjs",  # Node scripts
    ".jar", ".class",  # Java
    ".so", ".dylib",  # Shared libraries
}

CAUTION_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".env.local", ".env.production",
    ".sql", ".db", ".sqlite",
    ".pem", ".key", ".crt", ".cer", ".p12", ".pfx",
    ".csv",  # Can contain sensitive data
}


class FilesystemGuard:
    """Deterministic filesystem security boundary enforcer."""

    def __init__(self, workspace_roots: list[str] = None, extra_protected: list[str] = None):
        self.workspace_roots = [
            self._normalize(r) for r in (workspace_roots or [])
        ]
        
        # Build protected patterns based on OS
        if os.name == "nt":
            self.protected_patterns = list(PROTECTED_PATH_PATTERNS_WINDOWS)
        else:
            self.protected_patterns = list(PROTECTED_PATH_PATTERNS_LINUX)
        
        if extra_protected:
            self.protected_patterns.extend(extra_protected)
        
        log.info("🛡️ FilesystemGuard initialized | workspaces=%d | protected_patterns=%d",
                 len(self.workspace_roots), len(self.protected_patterns))

    @staticmethod
    def _normalize(path_str: str) -> str:
        """Normalize a path: resolve .., resolve symlinks, normalize separators, lowercase on Windows."""
        try:
            p = Path(path_str).resolve()
            normalized = str(p)
            # Normalize to forward slashes for consistent matching
            normalized = normalized.replace("\\", "/")
            # Case-insensitive on Windows
            if os.name == "nt":
                normalized = normalized.lower()
            return normalized
        except (OSError, ValueError) as e:
            log.warning("Path normalization failed for '%s': %s", path_str, e)
            return path_str.replace("\\", "/")

    def _check_symlink_safety(self, path_str: str) -> tuple[bool, str]:
        """Check if a path contains symlinks that escape the workspace."""
        try:
            p = Path(path_str)
            if not p.exists():
                # Non-existent paths can't have symlinks — check parent chain
                p = p.parent
            
            # Walk up the path checking for symlinks
            current = p
            while current != current.parent:
                if current.is_symlink():
                    real_target = str(current.resolve()).replace("\\", "/")
                    if os.name == "nt":
                        real_target = real_target.lower()
                    
                    # Check if the symlink target is within a workspace
                    in_workspace = any(
                        real_target.startswith(root) for root in self.workspace_roots
                    )
                    if not in_workspace:
                        return False, f"Symlink at '{current}' resolves to '{real_target}' outside workspace"
                current = current.parent
            
            return True, "OK"
        except (OSError, ValueError) as e:
            return False, f"Symlink check failed: {e}"

    def _is_in_workspace(self, normalized_path: str) -> bool:
        """Check if a normalized path is within any approved workspace root."""
        if not self.workspace_roots:
            return True  # No workspace restriction configured
        return any(normalized_path.startswith(root) for root in self.workspace_roots)

    def _is_protected(self, normalized_path: str) -> tuple[bool, str]:
        """Check if a path matches any protected pattern."""
        for pattern in self.protected_patterns:
            # Normalize pattern for matching
            norm_pattern = pattern.replace("\\", "/")
            if os.name == "nt":
                norm_pattern = norm_pattern.lower()
            
            if fnmatch.fnmatch(normalized_path, norm_pattern):
                return True, f"Matches protected pattern: '{pattern}'"
        
        return False, ""

    def _classify_file_risk(self, path_str: str, operation: FileOperation) -> FileRiskLevel:
        """Classify file risk based on extension and operation."""
        ext = Path(path_str).suffix.lower()
        
        if ext in BLOCKED_EXTENSIONS:
            return FileRiskLevel.BLOCKED
        
        if operation == FileOperation.EXECUTE:
            if ext in DANGEROUS_EXTENSIONS or ext in BLOCKED_EXTENSIONS:
                return FileRiskLevel.DANGEROUS
        
        if ext in DANGEROUS_EXTENSIONS and operation in (
            FileOperation.CREATE, FileOperation.MODIFY
        ):
            return FileRiskLevel.DANGEROUS
        
        if ext in CAUTION_EXTENSIONS:
            return FileRiskLevel.CAUTION
        
        return FileRiskLevel.SAFE

    @staticmethod
    def classify_operation(action_verb: str) -> FileOperation:
        """Map a human/tool action verb to a FileOperation enum."""
        verb_lower = action_verb.lower().strip()
        
        mapping = {
            "read": FileOperation.READ,
            "read_file": FileOperation.READ,
            "view": FileOperation.READ,
            "cat": FileOperation.READ,
            "type": FileOperation.READ,
            "list": FileOperation.LIST,
            "ls": FileOperation.LIST,
            "dir": FileOperation.LIST,
            "create": FileOperation.CREATE,
            "write": FileOperation.CREATE,
            "write_file": FileOperation.CREATE,
            "touch": FileOperation.CREATE,
            "modify": FileOperation.MODIFY,
            "edit": FileOperation.MODIFY,
            "append": FileOperation.MODIFY,
            "rename": FileOperation.RENAME,
            "move": FileOperation.RENAME,
            "mv": FileOperation.RENAME,
            "delete": FileOperation.DELETE,
            "remove": FileOperation.DELETE,
            "rm": FileOperation.DELETE,
            "del": FileOperation.DELETE,
            "unlink": FileOperation.DELETE,
            "rmdir": FileOperation.RECURSIVE_DELETE,
            "rm -rf": FileOperation.RECURSIVE_DELETE,
            "recursive_delete": FileOperation.RECURSIVE_DELETE,
            "shutil.rmtree": FileOperation.RECURSIVE_DELETE,
            "execute": FileOperation.EXECUTE,
            "run": FileOperation.EXECUTE,
            "exec": FileOperation.EXECUTE,
        }
        
        return mapping.get(verb_lower, FileOperation.READ)

    def assess(self, path_str: str, operation: FileOperation) -> PathAssessment:
        """Full filesystem security assessment for a path + operation."""
        reasons = []
        
        # 1. Normalize
        normalized = self._normalize(path_str)
        
        # 2. Symlink safety
        symlink_safe, symlink_reason = self._check_symlink_safety(path_str)
        if not symlink_safe:
            reasons.append(symlink_reason)
        
        # 3. Workspace boundary
        in_workspace = self._is_in_workspace(normalized)
        if not in_workspace:
            reasons.append(f"Path '{normalized}' is outside all workspace roots")
        
        # 4. Protected path check
        is_protected, protected_reason = self._is_protected(normalized)
        if is_protected:
            reasons.append(protected_reason)
        
        # 5. File type risk
        file_risk = self._classify_file_risk(normalized, operation)
        if file_risk == FileRiskLevel.BLOCKED:
            reasons.append(f"File extension is blocked: '{Path(normalized).suffix}'")
        elif file_risk == FileRiskLevel.DANGEROUS:
            reasons.append(f"Dangerous file type for operation '{operation.value}': '{Path(normalized).suffix}'")
        
        # 6. Decision logic
        allowed = True
        requires_approval = False
        
        # DENY: protected paths for write/delete/execute
        if is_protected and operation not in (FileOperation.READ, FileOperation.LIST):
            allowed = False
            reasons.append("DENIED: Write/Delete/Execute on protected path")
        
        # DENY: blocked file types for create/modify/execute
        if file_risk == FileRiskLevel.BLOCKED and operation in (
            FileOperation.CREATE, FileOperation.MODIFY, FileOperation.EXECUTE
        ):
            allowed = False
            reasons.append("DENIED: Blocked file type")
        
        # DENY: symlink escape
        if not symlink_safe:
            allowed = False
            reasons.append("DENIED: Symlink escapes workspace boundary")
        
        # REQUIRE_APPROVAL: outside workspace
        if not in_workspace and operation != FileOperation.READ:
            allowed = False
            requires_approval = True
            reasons.append("APPROVAL REQUIRED: Operation outside workspace")
        
        # REQUIRE_APPROVAL: dangerous operations
        if operation in (FileOperation.DELETE, FileOperation.RECURSIVE_DELETE):
            requires_approval = True
            reasons.append("APPROVAL REQUIRED: Destructive operation")
        
        # REQUIRE_APPROVAL: dangerous file types
        if file_risk == FileRiskLevel.DANGEROUS and allowed:
            requires_approval = True
            reasons.append("APPROVAL REQUIRED: Dangerous file type")
        
        # READ in workspace is always allowed (if not symlink-escaped)
        if operation in (FileOperation.READ, FileOperation.LIST) and in_workspace and symlink_safe:
            allowed = True
            requires_approval = False
        
        return PathAssessment(
            normalized_path=normalized,
            is_in_workspace=in_workspace,
            is_protected=is_protected,
            file_risk=file_risk,
            operation=operation,
            reasons=reasons,
            allowed=allowed,
            requires_approval=requires_approval,
        )
