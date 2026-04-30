"""
Pihu — Hardware Profiler & Setup Wizard
Evaluates local OS capabilities (RAM, CPU, VRAM) to calculate an execution Tier.
Safeguards the OS from OOM crashes by dynamically downgrading context windows.
"""

import os
import subprocess
import logging
from dataclasses import dataclass
from typing import Dict, Any

try:
    import psutil
except ImportError:
    psutil = None

log = logging.getLogger("HARDWARE")

@dataclass
class HardwareProfile:
    ram_gb: float
    cpu_cores: int
    vram_gb: float
    gpu_name: str
    tier: int
    recommended_model: str
    max_context: int
    capabilities_disabled: list[str]


class SystemProfiler:
    """Detects system constraints to establish execution boundaries."""

    def __init__(self):
        self.profile = None

    def _get_ram_gb(self) -> float:
        if psutil:
            return psutil.virtual_memory().total / (1024 ** 3)
        return 8.0  # Safe fallback

    def _get_cpu_cores(self) -> int:
        if psutil:
            return psutil.cpu_count(logical=False) or 4
        return 4

    def _get_gpu_info(self) -> tuple[float, str]:
        """Detects GPU VRAM across NVIDIA, AMD, and Intel GPUs.
        Priority: NVIDIA (nvidia-smi) -> AMD (rocm-smi) -> Intel (xe-smi) -> None
        """
        # 1. Try NVIDIA first (most common)
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,name", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                if lines:
                    parts = lines[0].split(", ")
                    if len(parts) >= 2:
                        mem_mb = float(parts[0].strip())
                        name = parts[1].strip()
                        return mem_mb / 1024.0, name
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        # 2. Try AMD ROCm
        try:
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--csv"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                for line in lines[1:]:  # Skip header
                    parts = line.split(",")
                    if len(parts) >= 2:
                        mem_bytes = float(parts[1].strip())
                        return mem_bytes / (1024 ** 3), "AMD GPU (ROCm)"
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        # 3. Try Intel Level Zero
        try:
            result = subprocess.run(
                ["xpu-smi", "-d", "0", "-q"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                # Intel GPU detected, estimate based on common configurations
                return 8.0, "Intel Arc/Xe GPU"
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        # 4. Try Intel GPU tools (older)
        try:
            result = subprocess.run(
                ["intel_gpu_top", "-L"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                return 4.0, "Intel Integrated GPU"
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        # 5. Try Windows WMI for Intel/AMD on Windows
        if os.name == 'nt':
            try:
                import wmi
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    gpu_name = gpu.Name.lower() if gpu.Name else ""
                    if 'intel' in gpu_name or 'amd' in gpu_name or 'ati' in gpu_name:
                        # Estimate from AdapterRAM (if available)
                        adapter_ram = getattr(gpu, 'AdapterRAM', None)
                        if adapter_ram:
                            return adapter_ram / (1024 ** 3), gpu.Name
            except (ImportError, Exception):
                pass

        return 0.0, "None / Integrated"

    def evaluate(self) -> HardwareProfile:
        """Determines the tier of the system."""
        ram = self._get_ram_gb()
        cpu = self._get_cpu_cores()
        vram, gpu_name = self._get_gpu_info()

        # Check for User Override
        override = os.getenv("PIHU_OVERRIDE_TIER")
        tier = None
        
        if override and override.isdigit():
            tier = int(override)
            log.warning("⚠️ HARDWARE TIER OVERRIDE ACTIVE: Enforcing Tier %d", tier)

        if not tier:
            if ram < 12.0 or (ram < 16.0 and vram < 4.0):
                tier = 1
            elif ram >= 32.0 and vram >= 12.0:
                tier = 3
            else:
                tier = 2

        # Map capabilities based on Tier
        if tier == 1:
            rec_model = "phi3:mini"
            max_ctx = 2048
            disabled = ["VisionAnalysis", "HeavySwarmConcurrency"]
        elif tier == 2:
            rec_model = "llama3.2:3b" # or qwen2.5:3b
            max_ctx = 4096
            disabled = ["HeavySwarmConcurrency"]
        else:
            rec_model = "llama3.1:8b"
            max_ctx = 8192
            disabled = []

        self.profile = HardwareProfile(
            ram_gb=ram,
            cpu_cores=cpu,
            vram_gb=vram,
            gpu_name=gpu_name,
            tier=tier,
            recommended_model=rec_model,
            max_context=max_ctx,
            capabilities_disabled=disabled
        )
        return self.profile

    def print_splash_screen(self):
        """Displays hardware evaluation and setup wizard instructions."""
        if not self.profile:
            self.evaluate()
            
        p = self.profile
        log.info("=" * 50)
        log.info(" 🖥️  SYSTEM PROFILER: HARDWARE CHECK COMPLETE")
        log.info("=" * 50)
        log.info(f" CPU Cores : {p.cpu_cores}")
        log.info(f" System RAM: {p.ram_gb:.1f} GB")
        log.info(f" GPU VRAM  : {p.vram_gb:.1f} GB ({p.gpu_name})")
        log.info("-" * 50)
        
        tier_labels = {1: "Low-End (Tier 1)", 2: "Mid-Range (Tier 2)", 3: "High-End (Tier 3)"}
        log.info(f" ⚙️ TIER MAPPING: {tier_labels.get(p.tier, 'Unknown')}")
        log.info(f" 🧠 IDEAL MODEL: {p.recommended_model}")
        log.info(f" 📦 MAX CONTEXT: {p.max_context} tokens")
        
        if p.capabilities_disabled:
            log.warning(" 🚫 DISABLED FEATURES: %s", ", ".join(p.capabilities_disabled))
            
        log.info("=" * 50)
        log.info(" 🛠️ SETUP WIZARD (BYOM)")
        log.info(f" Ensure Ollama is running, then execute this command in your terminal:")
        log.info(f"      ollama pull {p.recommended_model}")
        log.info("=" * 50)

# Global singleton
system_profiler = SystemProfiler()
