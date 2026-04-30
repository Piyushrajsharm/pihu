"""
Pihu — Sandbox Snapshot Engine
Creates physical redundant snapshots of the execution workspace to gracefully revert any destructive code loops.
"""

import os
import shutil
import filecmp
import difflib
from pathlib import Path
from datetime import datetime
from logger import get_logger

log = get_logger("SNAPSHOT")

class SnapshotEngine:
    """Handles deep-copy directory snapshots to provide absolute code-rollback guarantees."""
    
    def __init__(self, root_dir: str = ".pihu"):
        self.snapshots_dir = Path(root_dir) / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        
    def take_snapshot(self, target_workspace: Path | str) -> Path | None:
        """Dupe the target directory so we can revert if things explode."""
        target_path = Path(target_workspace)
        if not target_path.exists():
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = self.snapshots_dir / f"workspace_backup_{timestamp}"
        
        try:
            log.info("📸 Taking OS-level snapshot of %s -> %s", target_path.name, backup_path.name)
            shutil.copytree(str(target_path), str(backup_path))
            return backup_path
        except Exception as e:
            log.error("Failed to take workspace snapshot, rollback impossible: %s", e)
            return None
            
    def rollback(self, target_workspace: Path | str, snapshot_path: Path | str) -> bool:
        """Destroy the active workspace and restore from the snapshot."""
        target_path = Path(target_workspace)
        backup_path = Path(snapshot_path)
        
        if not backup_path.exists():
            log.error("Cannot rollback: Snapshot %s does not exist.", backup_path)
            return False
            
        try:
            log.warning("⏪ Attempting Workspace Rollback from %s", backup_path.name)
            # Nuke the corrupted target
            if target_path.exists():
                shutil.rmtree(str(target_path), ignore_errors=True)
                
            # Restore the pristine snapshot
            shutil.copytree(str(backup_path), str(target_path))
            log.info("✅ Workspace successfully restored to pre-execution state.")
            return True
        except Exception as e:
            log.error("CRITICAL: Failed to rollback workspace: %s", e)
            return False
            
    def cleanup(self, snapshot_path: Path | str):
        """Delete a snapshot once the execution is verified as safe."""
        backup_path = Path(snapshot_path)
        if backup_path.exists():
            try:
                shutil.rmtree(str(backup_path), ignore_errors=True)
                log.debug("🗑️ Discarded safe snapshot %s", backup_path.name)
            except Exception as e:
                log.error("Failed to cleanup snapshot: %s", e)

    def generate_diff(self, target_workspace: Path | str, snapshot_path: Path | str) -> str:
        """Calculates exact line mutations out of the active workspace."""
        target_path = Path(target_workspace)
        backup_path = Path(snapshot_path)
        
        if not target_path.exists() or not backup_path.exists():
            return ""
            
        diff_output = []
        
        # We perform a shallow compare using dircmp
        match = filecmp.dircmp(str(backup_path), str(target_path))
        
        for name in match.left_only:
            diff_output.append(f"[- DELETED] {name}")
            
        for name in match.right_only:
            diff_output.append(f"[+ CREATED] {name}")
            
        for name in match.diff_files:
            try:
                backup_file = backup_path / name
                target_file = target_path / name
                
                # Check if it's textual before doing unified_diff (skip binaries)
                # Quick binary check: read first 1024 bytes and look for nulls
                with open(target_file, 'rb') as f:
                    if b'\0' in f.read(1024):
                        diff_output.append(f"[~ MODIFIED BINARY] {name}")
                        continue
                        
                with open(backup_file, 'r', encoding='utf-8') as b_f:
                    b_lines = b_f.readlines()
                with open(target_file, 'r', encoding='utf-8') as t_f:
                    t_lines = t_f.readlines()
                    
                diff = difflib.unified_diff(b_lines, t_lines, fromfile=f"{name} (Old)", tofile=f"{name} (New)")
                diff_str = "".join(list(diff))
                if diff_str:
                    diff_output.append(f"\n[~ MODIFIED TEXT] {name}\n{diff_str}")
            except Exception:
                diff_output.append(f"[~ MODIFIED] {name} (Unreadable text delta)")
                
        return "\n".join(diff_output)
