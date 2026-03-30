"""
Pihu — Hybrid CPU/GPU Compute Scheduler
Monitors system resources and decides CPU vs GPU execution per task.
Implements auto-degradation and graceful GPU fallback.
"""

import time
import subprocess
import threading
from dataclasses import dataclass
from typing import Optional

import psutil

from logger import get_logger

log = get_logger("SCHEDULER")


@dataclass
class SystemStats:
    cpu_percent: float
    ram_percent: float
    ram_used_mb: float
    ram_total_mb: float
    vram_used_mb: float
    vram_total_mb: float
    gpu_available: bool


class SystemMonitor:
    """Polls CPU, RAM, and VRAM usage."""

    def __init__(self):
        self._gpu_checked = False
        self._has_gpu = False

    def get_stats(self) -> SystemStats:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()

        vram_used, vram_total, gpu_ok = self._get_vram()

        return SystemStats(
            cpu_percent=cpu,
            ram_percent=mem.percent,
            ram_used_mb=mem.used / (1024 ** 2),
            ram_total_mb=mem.total / (1024 ** 2),
            vram_used_mb=vram_used,
            vram_total_mb=vram_total,
            gpu_available=gpu_ok,
        )

    def _get_vram(self) -> tuple[float, float, bool]:
        """Try to read VRAM via rocm-smi (AMD) or fallback."""
        try:
            # Try AMD ROCm
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--csv"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines[1:]:  # Skip header
                    parts = line.split(",")
                    if len(parts) >= 2:
                        used = float(parts[0]) / (1024 ** 2)  # Bytes → MB
                        total = float(parts[1]) / (1024 ** 2)
                        self._has_gpu = True
                        return used, total, True
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

        try:
            # Try nvidia-smi as fallback (in case of NVIDIA GPU)
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,nounits,noheader"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) == 2:
                    self._has_gpu = True
                    return float(parts[0].strip()), float(parts[1].strip()), True
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

        return 0.0, 0.0, False


class ComputeScheduler:
    """Decides CPU vs GPU for each task type.
    
    GPU is NOT always-on. It is used selectively based on:
    - Task type (LLM, Vision → allowed; STT, TTS → avoid)
    - VRAM headroom (must stay ≤ 3GB)
    - System load (auto-degrade if overloaded)
    """

    # Tasks that can use GPU
    GPU_ALLOWED_TASKS = {"llm", "vision"}
    # Tasks that must always use CPU
    CPU_ONLY_TASKS = {"stt", "tts", "memory", "tools"}

    def __init__(self):
        from config import (
            MAX_VRAM_MB, CPU_THRESHOLD_PERCENT,
            RAM_THRESHOLD_PERCENT, GPU_COOLDOWN_SECONDS, FORCE_CPU,
        )

        self.monitor = SystemMonitor()
        self.max_vram_mb = MAX_VRAM_MB
        self.cpu_threshold = CPU_THRESHOLD_PERCENT
        self.ram_threshold = RAM_THRESHOLD_PERCENT
        self.gpu_cooldown_s = GPU_COOLDOWN_SECONDS
        self.force_cpu = FORCE_CPU

        # GPU crash tracking
        self._gpu_disabled = False
        self._gpu_disable_time: Optional[float] = None
        self._lock = threading.Lock()

        # Degradation state
        self._degraded = False

        log.info("ComputeScheduler initialized | force_cpu=%s", self.force_cpu)

    def get_device(self, task_type: str) -> str:
        """Return 'cpu' or 'gpu' for the given task type.
        
        Args:
            task_type: One of 'llm', 'vision', 'stt', 'tts', 'memory', 'tools'
        """
        # CPU-only tasks never go to GPU
        if task_type in self.CPU_ONLY_TASKS:
            return "cpu"

        # Force CPU mode
        if self.force_cpu:
            return "cpu"

        # Check GPU cooldown
        with self._lock:
            if self._gpu_disabled:
                elapsed = time.time() - (self._gpu_disable_time or 0)
                if elapsed < self.gpu_cooldown_s:
                    return "cpu"
                else:
                    self._gpu_disabled = False
                    log.info("GPU cooldown expired, re-enabling GPU")

        # Check if task type is GPU-eligible
        if task_type not in self.GPU_ALLOWED_TASKS:
            return "cpu"

        # Check VRAM headroom
        if self.is_gpu_safe():
            return "gpu"

        return "cpu"

    def is_gpu_safe(self) -> bool:
        """Check if GPU has enough VRAM headroom."""
        try:
            stats = self.monitor.get_stats()
            if not stats.gpu_available:
                return False
            return stats.vram_used_mb < self.max_vram_mb
        except Exception:
            return False

    def is_gpu_available(self) -> bool:
        """Check if GPU is available and not in cooldown."""
        if self.force_cpu:
            return False
        with self._lock:
            if self._gpu_disabled:
                return False
        return self.is_gpu_safe()

    def on_gpu_crash(self):
        """Called when GPU operation fails. Disables GPU with cooldown."""
        with self._lock:
            self._gpu_disabled = True
            self._gpu_disable_time = time.time()
        log.error(
            "GPU CRASH detected! Disabling GPU for %ds",
            self.gpu_cooldown_s,
        )

    def get_system_stats(self) -> SystemStats:
        """Get current system resource stats."""
        return self.monitor.get_stats()

    def check_degradation(self) -> dict:
        """Check if system needs to degrade performance.
        
        Returns dict with recommended actions:
        - 'use_smaller_model': bool
        - 'reduce_context': bool
        - 'disable_gpu': bool
        """
        stats = self.monitor.get_stats()
        actions = {
            "use_smaller_model": False,
            "reduce_context": False,
            "disable_gpu": False,
        }

        if stats.cpu_percent > self.cpu_threshold:
            actions["use_smaller_model"] = True
            log.warning("CPU > %d%% → switching to smaller models", self.cpu_threshold)

        if stats.ram_percent > self.ram_threshold:
            actions["reduce_context"] = True
            log.warning("RAM > %d%% → reducing context + clearing cache", self.ram_threshold)

        if stats.gpu_available and stats.vram_used_mb > self.max_vram_mb:
            actions["disable_gpu"] = True
            self.on_gpu_crash()
            log.warning("VRAM > %dMB → disabling GPU", self.max_vram_mb)

        self._degraded = any(actions.values())
        return actions

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    def get_recommended_model(self) -> str:
        """Return the recommended LLM model based on system load."""
        from config import LOCAL_LLM_PRIMARY, LOCAL_LLM_FALLBACK
        
        if self._degraded:
            return LOCAL_LLM_FALLBACK
        return LOCAL_LLM_PRIMARY
