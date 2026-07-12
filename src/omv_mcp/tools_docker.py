"""Docker tools. Listings use explicit scalar `--format` fields, never
`{{json .}}` (which is pathologically slow on this host)."""

import asyncio
import json

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .common import docker_ps
from .local import run_local, run_shell


def _docker_table(argv: list[str], fields: list[str], timeout: int = 30) -> list:
    """Run a `docker ... --format <tab-joined scalars>` and parse rows."""
    fmt = "\t".join("{{." + f + "}}" for f in fields)
    res = run_local(argv + ["--format", fmt], timeout=timeout)
    if res["exit_code"] != 0:
        raise RuntimeError(res["stderr"].strip() or f"{argv[:2]} failed")
    rows = []
    for line in res["stdout"].splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        parts += [""] * (len(fields) - len(parts))
        rows.append(dict(zip(fields, parts)))
    return rows


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_containers(include_all: bool = True) -> list:
        """Docker containers with names/status/image (`docker ps`; include_all adds stopped)."""
        return docker_ps(include_all)

    @mcp.tool()
    def container_stats() -> list:
        """Live per-container CPU%, memory, net/block I/O (`docker stats --no-stream`)."""
        return _docker_table(
            ["docker", "stats", "--no-stream"],
            ["Name", "CPUPerc", "MemUsage", "MemPerc", "NetIO", "BlockIO"],
        )

    @mcp.tool()
    def container_inspect(name: str) -> dict:
        """Full `docker inspect` for one container (config, mounts, network, state)."""
        res = run_local(["docker", "inspect", name], timeout=30)
        if res["exit_code"] != 0:
            raise RuntimeError(res["stderr"].strip() or "docker inspect failed")
        data = json.loads(res["stdout"])
        return data[0] if isinstance(data, list) and data else data

    @mcp.tool()
    def list_images() -> list:
        """Docker images (repo, tag, id, size)."""
        return _docker_table(
            ["docker", "images"], ["Repository", "Tag", "ID", "Size", "CreatedSince"]
        )

    @mcp.tool()
    def list_volumes() -> list:
        """Docker volumes (name, driver, mountpoint)."""
        return _docker_table(
            ["docker", "volume", "ls"], ["Name", "Driver", "Mountpoint"]
        )

    @mcp.tool()
    def list_networks() -> list:
        """Docker networks (id, name, driver, scope)."""
        return _docker_table(
            ["docker", "network", "ls"], ["ID", "Name", "Driver", "Scope"]
        )

    @mcp.tool()
    def docker_system_df() -> list:
        """Disk usage + reclaimable space by images/containers/volumes/build cache
        (`docker system df`)."""
        res = run_local(
            ["docker", "system", "df", "--format", "{{json .}}"], timeout=30
        )
        if res["exit_code"] != 0:
            raise RuntimeError(res["stderr"].strip() or "docker system df failed")
        return [json.loads(l) for l in res["stdout"].splitlines() if l.strip()]

    @mcp.tool()
    def container_logs(name: str, tail: int = 50) -> str:
        """Last `tail` lines of a container's logs."""
        res = run_local(["docker", "logs", name, "--tail", str(tail)], timeout=30)
        # docker writes logs to both streams; return whatever came back.
        return (res["stdout"] + res["stderr"]).strip()

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    def restart_container(name: str) -> dict:
        """Restart a single container (seconds of downtime)."""
        res = run_local(["docker", "restart", name], timeout=60)
        if res["exit_code"] != 0:
            raise RuntimeError(res["stderr"].strip() or "docker restart failed")
        return {"restarted": res["stdout"].strip()}

    @mcp.tool()
    def start_container(name: str) -> dict:
        """Start a stopped container."""
        res = run_local(["docker", "start", name], timeout=60)
        if res["exit_code"] != 0:
            raise RuntimeError(res["stderr"].strip() or "docker start failed")
        return {"started": res["stdout"].strip()}

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    def stop_container(name: str, confirm: bool = False) -> dict:
        """Stop a running container (downtime until restarted). Requires confirm=True."""
        if not confirm:
            return {"refused": f"Pass confirm=True to stop '{name}'."}
        res = run_local(["docker", "stop", name], timeout=60)
        if res["exit_code"] != 0:
            raise RuntimeError(res["stderr"].strip() or "docker stop failed")
        return {"stopped": res["stdout"].strip()}

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Run a command inside a container (UNRESTRICTED)",
            destructiveHint=True,
        )
    )
    def docker_exec(name: str, cmd: str, timeout: int = 60) -> dict:
        """Run a shell command inside a container as its user. UNRESTRICTED --
        no allow/deny-list. Returns {stdout, stderr, exit_code}."""
        return run_local(["docker", "exec", name, "sh", "-c", cmd], timeout=timeout)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Prune unused Docker data", destructiveHint=True
        )
    )
    async def docker_prune(
        ctx: Context, confirm: bool = False, volumes: bool = False
    ) -> dict:
        """Reclaim space by removing stopped containers, dangling images, unused
        networks and build cache (`docker system prune -f`). Set volumes=True to
        also drop anonymous volumes (DELETES their data). Requires confirm=True."""
        if not confirm:
            return {
                "refused": "Pass confirm=True to prune. volumes=True also deletes "
                "anonymous volume data."
            }
        cmd = "docker system prune -f" + (" --volumes" if volumes else "")
        await ctx.info(f"Running: {cmd}")
        await ctx.report_progress(0, 1)
        res = await asyncio.to_thread(run_shell, cmd, timeout=300)
        await ctx.report_progress(1, 1)
        if res["exit_code"] != 0:
            raise RuntimeError(res["stderr"].strip() or "docker prune failed")
        out = res["stdout"].strip()
        await ctx.info("Prune complete")
        return {"output": out}
