"""Stdio smoke test: spawn the server in-process over stdio, list every
capability, and exercise a representative sample. Run on the NAS:
``uv run python tests/smoke_client.py``.
"""

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    # Spawn the same interpreter running this test (the venv python), so it works
    # whether launched via `uv run` or the venv python directly (as prod does).
    params = StdioServerParameters(command=sys.executable, args=["-m", "omv_mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"[ok] {len(names)} tools registered:")
            print("     " + ", ".join(sorted(names)))

            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            prompts = await session.list_prompts()
            print(f"[ok] resources: {[str(r.uri) for r in resources.resources]}")
            print(f"[ok] templates: {[t.uriTemplate for t in templates.resourceTemplates]}")
            print(f"[ok] prompts:   {[p.name for p in prompts.prompts]}")

            async def call(name, **kwargs):
                res = await session.call_tool(name, kwargs)
                text = res.content[0].text if res.content else ""
                print(f"\n[call] {name}({kwargs}) ->")
                print("     " + text[:400].replace("\n", "\n     "))

            # read-only sample across the groups
            await call("get_system_info")
            await call("storage_summary")
            await call("container_stats")
            await call("docker_system_df")
            await call("smart_health", device="sda")
            await call("available_updates")
            await call("cpu_temp")
            # destructive gates should refuse without confirm:
            await call("reboot")
            await call("docker_prune")

            # a resource and a prompt
            health = await session.read_resource("omv://health")
            print("\n[resource] omv://health ->")
            print("     " + health.contents[0].text[:300].replace("\n", "\n     "))

            prompt = await session.get_prompt("diagnose_storage_health", {})
            print("\n[prompt] diagnose_storage_health ->")
            print("     " + prompt.messages[0].content.text[:200].replace("\n", "\n     "))


if __name__ == "__main__":
    asyncio.run(main())
