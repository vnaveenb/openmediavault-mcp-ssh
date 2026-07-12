"""Users / groups (read) and OMV config-write tools.

Config-write tools (Phase 3) will live here; they all require confirm=True and
must apply staged changes via Config.applyChanges after set/delete.
"""

from mcp.server.fastmcp import FastMCP

from .omv_rpc import omv_rpc as _rpc


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_users() -> list:
        """Non-system OMV users."""
        return _rpc("UserMgmt", "enumerateUsers")

    @mcp.tool()
    def list_groups() -> list:
        """Non-system OMV groups."""
        return _rpc("UserMgmt", "enumerateGroups")
