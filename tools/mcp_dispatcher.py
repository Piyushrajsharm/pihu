"""
Pihu — MCP Dispatcher
Placeholder for MCP / Pencil SWARM integration.
"""

from logger import get_logger

log = get_logger("TOOL")


class MCPDispatcher:
    """MCP (Model Context Protocol) / Pencil SWARM integration.
    
    Dispatches complex tasks (like UI generation) to an MCP server.
    This is a placeholder — implement when MCP server is available.
    """

    def __init__(self):
        from config import MCP_ENDPOINT
        self.endpoint = MCP_ENDPOINT

        log.info("MCPDispatcher initialized | endpoint=%s", self.endpoint)

    def dispatch(self, task_spec: dict) -> dict:
        """Send a task to the MCP server.
        
        Args:
            task_spec: Dict with task description and parameters

        Returns:
            Result dict from MCP server
        """
        log.info("📡 MCP dispatch: %s", task_spec.get("task", "")[:50])

        try:
            import httpx

            response = httpx.post(
                f"{self.endpoint}/tasks",
                json=task_spec,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            log.info("📡 MCP result received")
            return result

        except Exception as e:
            log.error("MCP dispatch failed: %s", e)
            return {
                "status": "error",
                "message": f"MCP server unavailable: {str(e)}",
                "fallback": True,
            }

    @property
    def is_available(self) -> bool:
        """Check if MCP server is reachable."""
        try:
            import httpx
            response = httpx.get(
                f"{self.endpoint}/health",
                timeout=2,
            )
            return response.status_code == 200
        except Exception:
            return False
