"""Portainer stack tools."""

import asyncio

import requests
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from . import portainer


def _stack_action(fn, stack_id: int):
    """Run a portainer start/stop, turning a 409 into a friendly no-op note."""
    try:
        return fn(stack_id)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 409:
            return {"note": "already in the requested state", "stack_id": stack_id}
        raise


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_stacks() -> list:
        """Portainer stacks (id, name, status)."""
        return portainer.list_stacks()

    @mcp.tool()
    def get_stack_compose(stack_id: int) -> str:
        """The full compose file for a Portainer stack."""
        return portainer.get_stack_file(stack_id)

    @mcp.tool()
    def start_stack(stack_id: int):
        """Start a stopped stack (brings its containers up)."""
        return _stack_action(portainer.start_stack, stack_id)

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    async def stop_stack(ctx: Context, stack_id: int, confirm: bool = False):
        """Stop a running stack (takes all its containers down). Requires confirm=True."""
        if not confirm:
            return {"refused": f"Pass confirm=True to stop stack {stack_id}."}
        await ctx.info(f"Stopping stack {stack_id} …")
        result = await asyncio.to_thread(_stack_action, portainer.stop_stack, stack_id)
        await ctx.info("Stack stopped")
        return result

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    async def restart_stack(ctx: Context, stack_id: int, confirm: bool = False):
        """Stop then start a stack (downtime during the cycle). Requires confirm=True."""
        if not confirm:
            return {"refused": f"Pass confirm=True to restart stack {stack_id}."}
        await ctx.info(f"Stopping stack {stack_id} …")
        await asyncio.to_thread(_stack_action, portainer.stop_stack, stack_id)
        await ctx.report_progress(1, 2)
        await ctx.info(f"Starting stack {stack_id} …")
        result = await asyncio.to_thread(_stack_action, portainer.start_stack, stack_id)
        await ctx.report_progress(2, 2)
        return result

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Redeploy a Portainer stack with new compose",
            destructiveHint=True,
        )
    )
    async def update_stack(ctx: Context, stack_id: int, compose: str, confirm: bool = False):
        """Redeploy a stack with the given compose YAML. DESTRUCTIVE: recreates
        containers (brief downtime). Requires confirm=True. Existing Env is
        preserved automatically."""
        if not confirm:
            return {"refused": "Pass confirm=True to redeploy. This recreates containers."}
        await ctx.info(f"Redeploying stack {stack_id} (recreating containers) …")
        result = await asyncio.to_thread(portainer.update_stack, stack_id, compose)
        await ctx.info("Redeploy complete")
        return result
