"""Shared helpers used across the tool modules.

Keeps the per-domain ``tools_*`` modules thin. Nothing here talks to MCP; these
are plain functions over the local subprocess / omv-rpc helpers.
"""

import json

from .local import run_local
from .omv_rpc import omv_rpc as _rpc

# Standard OMV paginated-list params (return everything, unsorted).
ALL_PARAMS = {"start": 0, "limit": -1, "sortfield": None, "sortdir": None}

# Explicit scalar fields only for `docker ps`. `{{json .}}` serialises every
# container's full label/mount/network set, which is pathologically slow here
# (~9s for 3 containers, >30s for all 45); scalar fields return in ~20ms.
PS_FIELDS = ["ID", "Names", "Image", "State", "Status", "Ports", "CreatedAt"]


def docker_ps(include_all: bool):
    fmt = "\t".join("{{." + f + "}}" for f in PS_FIELDS)
    argv = ["docker", "ps", "--format", fmt]
    if include_all:
        argv.insert(2, "-a")
    res = run_local(argv, timeout=30)
    if res["exit_code"] != 0:
        raise RuntimeError(res["stderr"].strip() or "docker ps failed")
    rows = []
    for line in res["stdout"].splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        parts += [""] * (len(PS_FIELDS) - len(parts))
        rows.append(dict(zip(PS_FIELDS, parts)))
    return rows


def dev_path(device: str) -> str:
    """Normalise 'sda' / '/dev/sda' -> '/dev/sda'. Rejects nothing else; the
    caller passes it straight to smartctl, which validates."""
    device = device.strip()
    return device if device.startswith("/dev/") else f"/dev/{device}"


def physical_disks() -> list[str]:
    """Bare disk device names (no partitions), e.g. ['sda','sdb',...] via lsblk."""
    res = run_local(["lsblk", "-dn", "-o", "NAME,TYPE"], timeout=15)
    disks = []
    for line in res["stdout"].splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "disk":
            disks.append(parts[0])
    return disks


def smartctl_json(device: str, *opts: str, timeout: int = 30) -> dict:
    """Run ``smartctl -j <opts> /dev/<device>`` and return parsed JSON.

    smartctl emits JSON even on error (its exit code is a bitmask, so a non-zero
    status often just means a benign SMART flag), so we always parse stdout and
    surface whatever smartctl reported rather than raising on exit code.
    """
    res = run_local(["smartctl", "-j", *opts, dev_path(device)], timeout=timeout)
    try:
        return json.loads(res["stdout"])
    except json.JSONDecodeError:
        return {"_raw": res["stdout"], "_stderr": res["stderr"], "_exit": res["exit_code"]}


# --------------------------------------------------------------------------
# Composite collectors — shared by tools, resources, and prompts so there is a
# single source of truth for each derived view.
# --------------------------------------------------------------------------

def storage_summary() -> list:
    """Per-mount usage for the OS + data disks. Skips tmpfs/overlay/virtual."""
    res = run_local(
        ["df", "-B1", "--output=source,fstype,size,used,avail,pcent,target"],
        timeout=15,
    )
    rows = []
    for line in res["stdout"].splitlines()[1:]:
        p = line.split(None, 6)
        if len(p) != 7:
            continue
        source, fstype, size, used, avail, pcent, target = p
        if target != "/" and not target.startswith("/srv/"):
            continue
        rows.append(
            {
                "device": source,
                "mount": target,
                "fstype": fstype,
                "size_bytes": int(size),
                "used_bytes": int(used),
                "avail_bytes": int(avail),
                "used_pct": pcent,
            }
        )
    return rows


def disk_temperatures() -> list:
    """Current temperature (°C) of every physical disk."""
    out = []
    for dev in physical_disks():
        d = smartctl_json(dev, "-A")
        out.append({"device": dev, "temperature_c": d.get("temperature", {}).get("current")})
    return out


def health_report() -> dict:
    """Composite health snapshot: SMART overall status, disk temps, CPU temp,
    and filesystem usage. Backs the ``omv://health`` resource and the storage
    diagnosis prompt."""
    try:
        smart = _rpc("Smart", "getList", ALL_PARAMS)
    except Exception as e:  # pragma: no cover - surface, don't crash the report
        smart = {"_error": str(e)}
    try:
        cpu = _rpc("CpuTemp", "get")
    except Exception as e:
        cpu = {"_error": str(e)}
    return {
        "smart_overall": smart,
        "disk_temperatures": disk_temperatures(),
        "cpu_temp": cpu,
        "storage": storage_summary(),
    }
