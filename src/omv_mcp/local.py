"""Local subprocess helpers. The server runs ON the NAS as root, so these call
``omv-rpc`` / ``docker`` / ``df`` directly -- no SSH in the hot path.
"""

import os
import subprocess

# Non-login shells (e.g. `ssh host -- python ...`) get a minimal PATH; make sure
# /usr/sbin (omv-rpc) and /usr/bin (docker) are reachable regardless.
_ENV = {
    **os.environ,
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:"
    + os.environ.get("PATH", ""),
}


def run_local(argv, timeout=60, input_text=None):
    """Run an argv list (no shell) and return {stdout, stderr, exit_code}."""
    p = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_ENV,
        input=input_text,
    )
    return {"stdout": p.stdout, "stderr": p.stderr, "exit_code": p.returncode}


def run_shell(cmd, timeout=60):
    """Run a shell command string (pipes/globs allowed) via bash -c."""
    return run_local(["/bin/bash", "-c", cmd], timeout=timeout)
