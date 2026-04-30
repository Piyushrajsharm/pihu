"""
Pihu — Local Docker Sandbox Wrapper
Isolates all Python execution to a transient container ensuring OS governance.
Implements granular execution profiles, readonly mounts, and network-off by default.
"""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any, Tuple
from logger import get_logger

try:
    import docker
except ImportError:
    docker = None

log = get_logger("DOCKER-SANDBOX")

class DockerExecutor:
    """Transient, strongly isolated execution environment inside Docker."""

    def __init__(self, workspace_path: str = ".pihu/workspace", profile_name: str = "python_sandbox"):
        self.client = None
        self.workspace_host_path = Path(workspace_path).absolute()
        self.container_workspace_path = "/workspace"
        self.profile_name = profile_name

        from sandbox.execution_profiles import get_profile
        self.profile = get_profile(profile_name)

        from sandbox.snapshot_engine import SnapshotEngine
        self.snapshot_engine = SnapshotEngine()

        self.workspace_host_path.mkdir(parents=True, exist_ok=True)

        if docker:
            try:
                self.client = docker.from_env()
                self._ensure_image()
            except Exception as e:
                log.error("Failed to connect to Docker daemon: %s", e)
        else:
            log.warning("Docker SDK missing. 'pip install docker'")

    @property
    def is_available(self) -> bool:
        return self.client is not None

    def _ensure_image(self):
        """Pull the slim python image if it doesn't exist locally."""
        image_tag = "python:3.10-slim"
        try:
            self.client.images.get(image_tag)
        except docker.errors.ImageNotFound:
            log.info("Pulling base execution image: %s ...", image_tag)
            self.client.images.pull("python", tag="3.10-slim")

    def run_code(self, code_string: str, timeout: int = None) -> Tuple[str, str, int]:
        """
        Executes Python code in a transient sandbox container strictly scoped by ExecutionProfile.
        Returns: (stdout, stderr, exit_code)
        """
        if not self.is_available:
            return ("", "Execution Environment Unavailable", 1)
            
        timeout = timeout or self.profile.timeout_seconds

        # Unique run ID
        run_id = str(uuid.uuid4())[:8]
        
        # 1. Prepare temp directory for artifact export
        temp_dir_str = tempfile.mkdtemp(prefix=f"pihu_run_{run_id}_")
        temp_dir = Path(temp_dir_str)
        
        # Write code to the workspace so container can see it (host can write, container may only read)
        script_file = self.workspace_host_path / f"_temp_exec_{run_id}.py"
        try:
            script_file.write_text(code_string, encoding="utf-8")
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return ("", f"Failed to write transient execute file: {e}", 1)

        # 2. Build Volumes
        mode = "ro" if self.profile.workspace_mount_readonly else "rw"
        volumes = {
            str(self.workspace_host_path): {
                'bind': self.container_workspace_path,
                'mode': mode
            }
        }
        
        if self.profile.temp_rw_mount:
            volumes[str(temp_dir)] = {
                'bind': '/tmp/run',
                'mode': 'rw'
            }

        # 3. Security Assertions
        net_mode = self.profile.network_mode.value
        log.info("🚀 Launching Sandbox [%s] | Net: %s | RO: %s", 
                 self.profile.name, net_mode, self.profile.workspace_mount_readonly)

        try:
            # 4. Snapshot before we execute
            snapshot_path = self.snapshot_engine.take_snapshot(self.workspace_host_path)
            
            # 5. Run transient container
            # We use container.run with auto_remove=True but we may need to grab output first
            # Since we need a timeout, we run detached, wait, and grab logs.
            container = self.client.containers.run(
                "python:3.10-slim",
                command=["python", f"_temp_exec_{run_id}.py"],
                detach=True,
                volumes=volumes,
                network_mode=net_mode,
                working_dir=self.container_workspace_path,
                mem_limit=f"{self.profile.mem_limit_mb}m",
                memswap_limit=f"{self.profile.memswap_limit_mb}m",
                nano_cpus=self.profile.nano_cpus,
                pids_limit=self.profile.pids_limit,
                cap_drop=["ALL"] if self.profile.drop_all_capabilities else None,
                cap_add=self.profile.extra_capabilities or None
            )
            
            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get('StatusCode', 1)
                
                # Fetch logs
                logs = container.logs(stdout=True, stderr=True)
                # This is crude: in production we would demux stdout and stderr cleanly, 
                # but docker-py logs() on a stopped container combines them. 
                # We'll just return the full log as stdout and empty stderr.
                out_str = logs.decode("utf-8", errors="replace").strip()
                err_str = ""
            except Exception as e: # Timeout or other error
                container.stop(timeout=1)
                exit_code = 1
                out_str = ""
                err_str = f"Container terminated abruptly (Timeout {timeout}s?): {e}"
            finally:
                try:
                    container.remove(force=True)
                except docker.errors.NotFound:
                    pass

            # 6. Artifact export
            # Anything written to /tmp/run by the container is copied to workspace/outputs
            outputs_dir = self.workspace_host_path / "outputs"
            outputs_dir.mkdir(exist_ok=True)
            for exported_file in temp_dir.rglob("*"):
                if exported_file.is_file():
                    rel_path = exported_file.relative_to(temp_dir)
                    dest = outputs_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(exported_file, dest)

            # 7. Cleanup
            if script_file.exists():
                script_file.unlink()
            shutil.rmtree(temp_dir, ignore_errors=True)

            # 8. Snapshot Rollback on failure
            if exit_code != 0:
                if snapshot_path:
                    self.snapshot_engine.rollback(self.workspace_host_path, snapshot_path)
                    err_str += "\n\n[System]: Execution crashed. Workspace rolled back to pre-execution state automatically."
            else:
                if snapshot_path:
                    diff = self.snapshot_engine.generate_diff(self.workspace_host_path, snapshot_path)
                    if diff:
                        log.info("Workspace lines mutated:\n%s", diff)
                    self.snapshot_engine.cleanup(snapshot_path)
                
            return (out_str, err_str, exit_code)
            
        except Exception as e:
            if script_file.exists():
                script_file.unlink()
            shutil.rmtree(temp_dir, ignore_errors=True)
            return ("", f"Docker Execution Error: {str(e)}", 1)

    def cleanup(self):
        """No persistent container to kill in V2."""
        pass
