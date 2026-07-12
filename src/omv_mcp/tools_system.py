"""System + maintenance tools.

Read tools are unrestricted. ``run_command`` is UNRESTRICTED root by design.
``reboot`` / ``shutdown`` / ``apply_updates`` require ``confirm=True``.
"""

import asyncio
import json

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .common import ALL_PARAMS
from .local import run_local, run_shell
from .omv_rpc import omv_rpc as _rpc

# systemd units worth a default health glance when the caller passes none.
_DEFAULT_UNITS = ["docker", "ssh", "smbd", "nmbd", "cron", "nfs-server"]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_system_info() -> dict:
        """OMV/host info: hostname, OMV version, kernel, CPU, memory, uptime, load."""
        return _rpc("System", "getInformation")

    @mcp.tool()
    def disk_usage() -> str:
        """Human-readable filesystem usage (`df -h`)."""
        return run_shell("df -h").get("stdout", "")

    @mcp.tool()
    def list_block_devices() -> dict:
        """Block devices with size/model/serial/fs/mountpoint/uuid (`lsblk -J`)."""
        res = run_local(
            ["lsblk", "-J", "-o", "NAME,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINT,UUID"],
            timeout=30,
        )
        if res["exit_code"] != 0:
            raise RuntimeError(res["stderr"].strip() or "lsblk failed")
        return json.loads(res["stdout"])

    @mcp.tool()
    def top_processes(sort_by: str = "cpu", limit: int = 15) -> list:
        """Top processes by cpu or mem (`ps`, fast). sort_by is 'cpu' or 'mem'."""
        key = "-pmem" if sort_by == "mem" else "-pcpu"
        res = run_local(
            ["ps", "-eo", "pid,user,pcpu,pmem,rss,comm", "--sort", key],
            timeout=15,
        )
        rows = []
        lines = res["stdout"].splitlines()
        for line in lines[1 : limit + 1]:
            p = line.split(None, 5)
            if len(p) == 6:
                rows.append(
                    {
                        "pid": int(p[0]),
                        "user": p[1],
                        "cpu_pct": float(p[2]),
                        "mem_pct": float(p[3]),
                        "rss_kb": int(p[4]),
                        "command": p[5],
                    }
                )
        return rows

    @mcp.tool()
    def memory_info() -> dict:
        """RAM and swap usage in bytes (`free -b`)."""
        res = run_local(["free", "-b"], timeout=15)
        out = {}
        for line in res["stdout"].splitlines():
            parts = line.split()
            if parts and parts[0] == "Mem:":
                out["mem"] = {
                    "total": int(parts[1]), "used": int(parts[2]), "free": int(parts[3]),
                    "shared": int(parts[4]), "buff_cache": int(parts[5]), "available": int(parts[6]),
                }
            elif parts and parts[0] == "Swap:":
                out["swap"] = {"total": int(parts[1]), "used": int(parts[2]), "free": int(parts[3])}
        return out

    @mcp.tool()
    def available_updates() -> dict:
        """APT packages with pending upgrades (name/versions only). {count, packages}."""
        pkgs = _rpc("Apt", "enumerateUpgraded", ALL_PARAMS) or []
        keep = ("name", "oldversion", "version", "architecture", "repository", "priority")
        trimmed = [{k: p.get(k) for k in keep} for p in pkgs]
        return {"count": len(trimmed), "packages": trimmed}

    @mcp.tool()
    def service_status(units: list[str] | None = None) -> dict:
        """systemd active/enabled state per unit (`systemctl`, fast). Defaults to
        a common NAS set if none given."""
        units = units or _DEFAULT_UNITS
        out = {}
        for u in units:
            active = run_local(["systemctl", "is-active", u], timeout=10)["stdout"].strip()
            enabled = run_local(["systemctl", "is-enabled", u], timeout=10)["stdout"].strip()
            out[u] = {"active": active or "unknown", "enabled": enabled or "unknown"}
        return out

    @mcp.tool()
    def service_logs(unit: str, lines: int = 50) -> str:
        """Last `lines` journal entries for a systemd unit (`journalctl -u`)."""
        res = run_local(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"],
            timeout=30,
        )
        return (res["stdout"] + res["stderr"]).strip()

    @mcp.tool()
    def network_info() -> list:
        """Network interfaces with addresses (`ip -j addr`); virtual docker/veth
        interfaces are filtered out for signal."""
        res = run_local(["ip", "-j", "addr"], timeout=15)
        try:
            ifaces = json.loads(res["stdout"])
        except json.JSONDecodeError:
            return [{"_raw": res["stdout"]}]
        out = []
        for i in ifaces:
            name = i.get("ifname", "")
            if name.startswith(("veth", "br-")):
                continue
            out.append(
                {
                    "name": name,
                    "state": i.get("operstate"),
                    "mac": i.get("address"),
                    "addresses": [
                        f"{a.get('local')}/{a.get('prefixlen')}" for a in i.get("addr_info", [])
                    ],
                }
            )
        return out

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Run a raw shell command as root (UNRESTRICTED)",
            destructiveHint=True,
        )
    )
    def run_command(cmd: str, timeout: int = 60) -> dict:
        """Run an arbitrary shell command on the NAS as root. UNRESTRICTED and
        UNGUARDED -- there is no allow/deny-list. Prefer the specific tools
        (omv_rpc, docker, stacks) over hand-editing config. Returns
        {stdout, stderr, exit_code}."""
        return run_shell(cmd, timeout=timeout)

    @mcp.tool(annotations=ToolAnnotations(title="Apply APT upgrades", destructiveHint=True))
    async def apply_updates(ctx: Context, confirm: bool = False) -> dict:
        """Install pending APT upgrades (`apt-get -y upgrade`, noninteractive).
        Requires confirm=True. Run `available_updates` first to see what changes.
        Returns {exit_code, output}."""
        if not confirm:
            return {"refused": "Pass confirm=True to apply APT upgrades."}
        await ctx.info("Applying APT upgrades (apt-get -y upgrade) …")
        await ctx.report_progress(0, 1)
        res = await asyncio.to_thread(
            run_shell,
            "DEBIAN_FRONTEND=noninteractive apt-get -y upgrade",
            timeout=1800,
        )
        await ctx.report_progress(1, 1)
        await ctx.info("apt-get upgrade finished")
        return {"exit_code": res["exit_code"], "output": (res["stdout"] + res["stderr"]).strip()}

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    def reboot(confirm: bool = False):
        """Reboot the NAS. Requires confirm=True."""
        if not confirm:
            return {"refused": "Pass confirm=True to reboot the NAS."}
        return _rpc("System", "reboot", {"delay": 0})

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    def shutdown(confirm: bool = False):
        """Power off the NAS. Requires confirm=True."""
        if not confirm:
            return {"refused": "Pass confirm=True to shut down the NAS."}
        return _rpc("System", "shutdown", {"delay": 0})
