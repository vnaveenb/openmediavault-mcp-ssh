"""Argument completion for resource templates and prompt arguments.

Per the MCP spec, completion applies to prompt arguments and resource-template
arguments (not tool inputs). We complete:
- container names for ``omv://container/{name}/logs``
- stack ids for ``omv://stack/{stack_id}/compose``
- shared-folder names for the ``audit_shares_and_permissions`` prompt's ``share`` arg
"""

from mcp.server.fastmcp import FastMCP
from mcp.types import Completion, PromptReference, ResourceTemplateReference

from . import portainer
from .common import docker_ps
from .omv_rpc import omv_rpc as _rpc


def _match(values: list[str], partial: str) -> Completion:
    partial = (partial or "").lower()
    hits = [v for v in values if partial in v.lower()]
    return Completion(values=hits[:100], total=len(hits), hasMore=len(hits) > 100)


def _container_names() -> list[str]:
    return [c["Names"] for c in docker_ps(True) if c.get("Names")]


def _stack_ids() -> list[str]:
    return [str(s["Id"]) for s in portainer.list_stacks() if "Id" in s]


def _share_names() -> list[str]:
    return [s.get("name", "") for s in (_rpc("ShareMgmt", "enumerateSharedFolders") or [])]


def register(mcp: FastMCP) -> None:
    @mcp.completion()
    async def handle_completion(ref, argument, context):
        try:
            name = getattr(argument, "name", "")
            value = getattr(argument, "value", "")
            if isinstance(ref, ResourceTemplateReference):
                uri = ref.uri
                if "container/{name}/logs" in uri and name == "name":
                    return _match(_container_names(), value)
                if "stack/{stack_id}/compose" in uri and name == "stack_id":
                    return _match(_stack_ids(), value)
            elif isinstance(ref, PromptReference):
                if ref.name == "audit_shares_and_permissions" and name == "share":
                    return _match(_share_names(), value)
        except Exception:
            # Completion is best-effort; never break the session over it.
            return None
        return None
