"""MCP resources: read-only NAS context any client can pull without a tool call.

Static-ish URIs return live snapshots; two resource templates expose per-object
data (container logs, stack compose).
"""

import json

from mcp.server.fastmcp import FastMCP

from . import common, portainer
from .local import run_local
from .omv_rpc import omv_rpc as _rpc


def _json(obj) -> str:
    return json.dumps(obj, indent=2, default=str)


def register(mcp: FastMCP) -> None:
    @mcp.resource("omv://system", name="System info", mime_type="application/json")
    def system_resource() -> str:
        """Live host/OMV info (hostname, version, kernel, cpu, memory, uptime)."""
        return _json(_rpc("System", "getInformation"))

    @mcp.resource(
        "omv://storage/overview", name="Storage overview", mime_type="application/json"
    )
    def storage_resource() -> str:
        """Per-mount usage for the OS + data disks."""
        return _json(common.storage_summary())

    @mcp.resource("omv://health", name="Health snapshot", mime_type="application/json")
    def health_resource() -> str:
        """Composite: SMART overall, disk temps, CPU temp, filesystem usage."""
        return _json(common.health_report())

    @mcp.resource("omv://stacks", name="Portainer stacks", mime_type="application/json")
    def stacks_resource() -> str:
        """Portainer stacks (id, name, status)."""
        return _json(portainer.list_stacks())

    # ---- resource templates (parameterised) ----
    @mcp.resource("omv://container/{name}/logs", mime_type="text/plain")
    def container_logs_resource(name: str) -> str:
        """Last 100 log lines for a container."""
        res = run_local(["docker", "logs", name, "--tail", "100"], timeout=30)
        return (res["stdout"] + res["stderr"]).strip()

    @mcp.resource("omv://stack/{stack_id}/compose", mime_type="text/yaml")
    def stack_compose_resource(stack_id: str) -> str:
        """Compose file for a Portainer stack."""
        return portainer.get_stack_file(int(stack_id))
