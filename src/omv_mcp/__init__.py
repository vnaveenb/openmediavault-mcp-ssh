"""omv-mcp: an MCP server that manages an OpenMediaVault NAS from on-box.

Runs on the NAS itself, so every tool is a *local* subprocess call to
``omv-rpc`` / ``docker`` / ``df`` (no per-call SSH). Consumed by MCP clients
over stdio, typically tunnelled with ``ssh root@<nas> -- python -m omv_mcp``.
"""

__version__ = "0.1.0"
