"""
Pihu — Execution Profiles
Defines deterministic, ring-fenced Docker profiles for different tool executors.
Used by DockerExecutor to apply granular CPU/RAM/Network caps.
"""
from dataclasses import dataclass, field
from enum import Enum

class NetworkMode(Enum):
    NONE = "none"
    BRIDGE = "bridge"
    HOST = "host"

@dataclass
class ExecutionProfile:
    name: str                           # e.g., 'python_sandbox', 'browser_sandbox'
    workspace_mount_readonly: bool      # true = ro, false = rw
    network_mode: NetworkMode           # none by default
    mem_limit_mb: int                   # soft limit
    memswap_limit_mb: int               # strict cap
    nano_cpus: int                      # CPU limit in nano (1 billion = 1 CPU)
    pids_limit: int                     # Max processes (stops fork bombs)
    timeout_seconds: int                # Hard execution kill
    ulimit_nofile: int                  # Max open files
    drop_all_capabilities: bool         # Docker --cap-drop=ALL
    extra_capabilities: list[str] = field(default_factory=list)
    temp_rw_mount: bool = True          # Mount a tmpfs at /tmp
    
# ── DEFAULT PROFILES ──
    
PYTHON_SANDBOX = ExecutionProfile(
    name="python_sandbox",
    workspace_mount_readonly=True,
    network_mode=NetworkMode.NONE,
    mem_limit_mb=512,
    memswap_limit_mb=512,
    nano_cpus=500_000_000,   # 0.5 CPU
    pids_limit=50,           # Prevent fork bombs
    timeout_seconds=120,
    ulimit_nofile=1024,
    drop_all_capabilities=True,
)

SHELL_SANDBOX = ExecutionProfile(
    name="shell_sandbox",
    workspace_mount_readonly=True,
    network_mode=NetworkMode.NONE,
    mem_limit_mb=256,
    memswap_limit_mb=256,
    nano_cpus=250_000_000,   # 0.25 CPU
    pids_limit=20,
    timeout_seconds=60,
    ulimit_nofile=512,
    drop_all_capabilities=True,
)

BROWSER_SANDBOX = ExecutionProfile(
    name="browser_sandbox",
    workspace_mount_readonly=False, # Browser needs RW cache
    network_mode=NetworkMode.BRIDGE, # Network enabled! But controlled by NetworkGuard
    mem_limit_mb=1024,
    memswap_limit_mb=2048,
    nano_cpus=1_000_000_000, # 1 CPU
    pids_limit=200,          # Chromium spans many procs
    timeout_seconds=300,
    ulimit_nofile=4096,
    drop_all_capabilities=True,
)

PLUGIN_SANDBOX = ExecutionProfile(
    name="plugin_sandbox",
    workspace_mount_readonly=True,
    network_mode=NetworkMode.NONE,
    mem_limit_mb=256,
    memswap_limit_mb=256,
    nano_cpus=250_000_000,   # 0.25 CPU
    pids_limit=30,
    timeout_seconds=60,
    ulimit_nofile=1024,
    drop_all_capabilities=True,
)

PROFILES = {
    p.name: p for p in [PYTHON_SANDBOX, SHELL_SANDBOX, BROWSER_SANDBOX, PLUGIN_SANDBOX]
}

def get_profile(name: str) -> ExecutionProfile:
    return PROFILES.get(name, PYTHON_SANDBOX)  # Fail closed: cheapest, most strict profile
