"""Storage + health tools (omv-rpc, smartctl, sensors, df)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import common
from .common import ALL_PARAMS, smartctl_json
from .local import run_local
from .omv_rpc import omv_rpc as _rpc


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_filesystems() -> list:
        """All filesystems OMV knows about (mounted or not)."""
        return _rpc("FileSystemMgmt", "enumerateFilesystems")

    @mcp.tool()
    def list_disks() -> list:
        """Physical disk devices known to OMV."""
        return _rpc("DiskMgmt", "enumerateDevices")

    @mcp.tool()
    def smart_status() -> dict:
        """S.M.A.R.T. overview per device (overall health status, from OMV)."""
        return _rpc("Smart", "getList", ALL_PARAMS)

    @mcp.tool()
    def smart_health(device: str) -> dict:
        """SMART overall-health self-assessment for one device (PASSED/FAILED).
        `device` is 'sda' or '/dev/sda'."""
        d = smartctl_json(device, "-H")
        status = d.get("smart_status")
        return {
            "device": device,
            "passed": status.get("passed") if isinstance(status, dict) else None,
            "messages": [m.get("string") for m in d.get("smartctl", {}).get("messages", [])],
        }

    @mcp.tool()
    def smart_attributes(device: str) -> dict:
        """Full SMART attribute table for one device (`smartctl -A`), plus current
        temperature and power-on hours. `device` is 'sda' or '/dev/sda'."""
        d = smartctl_json(device, "-A")
        table = d.get("ata_smart_attributes", {}).get("table", [])
        attrs = [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "value": a.get("value"),
                "worst": a.get("worst"),
                "thresh": a.get("thresh"),
                "raw": a.get("raw", {}).get("string"),
                "when_failed": a.get("when_failed") or None,
            }
            for a in table
        ]
        return {
            "device": device,
            "temperature_c": d.get("temperature", {}).get("current"),
            "power_on_hours": d.get("power_on_time", {}).get("hours"),
            "power_cycle_count": d.get("power_cycle_count"),
            "attributes": attrs or None,
            "messages": [m.get("string") for m in d.get("smartctl", {}).get("messages", [])] or None,
        }

    @mcp.tool()
    def smart_selftest_log(device: str) -> dict:
        """SMART self-test history for one device (`smartctl -l selftest`)."""
        d = smartctl_json(device, "-l", "selftest")
        return {
            "device": device,
            "table": d.get("ata_smart_self_test_log", {}).get("standard", {}).get("table"),
            "messages": [m.get("string") for m in d.get("smartctl", {}).get("messages", [])] or None,
        }

    @mcp.tool()
    def disk_temperatures() -> list:
        """Current temperature (°C) of every physical disk (`smartctl -A` per disk)."""
        return common.disk_temperatures()

    @mcp.tool(annotations=ToolAnnotations(title="Start a SMART self-test"))
    def run_smart_test(device: str, kind: str = "short", confirm: bool = False) -> dict:
        """Start a SMART self-test on a device. `kind` is 'short', 'long', or
        'conveyance'. The test runs in the background (adds drive load); poll
        results later with `smart_selftest_log`. Requires confirm=True."""
        if kind not in ("short", "long", "conveyance"):
            raise ValueError("kind must be short, long, or conveyance")
        if not confirm:
            return {"refused": f"Pass confirm=True to start a {kind} self-test on {device}."}
        d = smartctl_json(device, "-t", kind)
        return {
            "device": device,
            "kind": kind,
            "messages": [m.get("string") for m in d.get("smartctl", {}).get("messages", [])],
        }

    @mcp.tool()
    def cpu_temp() -> dict:
        """CPU temperature in °C (OMV CpuTemp plugin)."""
        return _rpc("CpuTemp", "get")

    @mcp.tool()
    def sensors_readout() -> dict:
        """All lm-sensors readings as structured JSON (`sensors -j`)."""
        import json

        res = run_local(["sensors", "-j"], timeout=15)
        try:
            return json.loads(res["stdout"])
        except json.JSONDecodeError:
            return {"_raw": res["stdout"], "_stderr": res["stderr"]}

    @mcp.tool()
    def storage_summary() -> list:
        """Per-mount usage for the OS + data disks (`df`): device, mount, fstype,
        total/used/avail bytes, and percent. Skips tmpfs/overlay/virtual mounts."""
        return common.storage_summary()

    @mcp.tool()
    def list_shared_folders() -> list:
        """OMV shared folders (name, path, device)."""
        return _rpc("ShareMgmt", "enumerateSharedFolders")

    @mcp.tool()
    def list_smb_shares() -> dict:
        """Configured SMB/CIFS shares."""
        return _rpc("SMB", "getShareList", ALL_PARAMS)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Call an arbitrary OMV RPC method (UNRESTRICTED)",
            destructiveHint=True,
        )
    )
    def omv_rpc(service: str, method: str, params: dict | None = None):
        """Generic OMV RPC passthrough: `omv-rpc -u admin <service> <method> <params>`.
        UNRESTRICTED -- can call mutating methods too. Discover methods by
        grepping /usr/share/openmediavault/engined/rpc/*.inc on the host."""
        return _rpc(service, method, params)
