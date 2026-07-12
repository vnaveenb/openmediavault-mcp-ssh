"""Thin wrapper over the local ``omv-rpc`` CLI.

Runs as ``omv-rpc -u admin <Service> <method> [<json-params>]`` on-box, which
needs no password (unlike the HTTP /rpc.php path the official server uses).
"""

import json

from .local import run_local

OMV_RPC = "/usr/sbin/omv-rpc"


class OmvRpcError(RuntimeError):
    """Raised when the omv-rpc CLI exits non-zero."""


def omv_rpc(service: str, method: str, params=None):
    """Call an OMV RPC method and return the parsed JSON result.

    ``params`` is a JSON-serialisable value (usually a dict) or None.
    """
    argv = [OMV_RPC, "-u", "admin", service, method]
    if params is not None:
        argv.append(json.dumps(params))
    res = run_local(argv, timeout=120)
    if res["exit_code"] != 0:
        detail = res["stderr"].strip() or res["stdout"].strip()
        raise OmvRpcError(f"omv-rpc {service}.{method} failed (exit {res['exit_code']}): {detail}")
    out = res["stdout"].strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out
