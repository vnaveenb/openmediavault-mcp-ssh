"""Command-execution seam — the ONLY module that runs commands.

Mode A (``OMV_HOST`` unset): this process runs ON the NAS; plain local
subprocess, no SSH in the hot path.

Mode B (``OMV_HOST`` set): this process runs anywhere (workstation/laptop);
the same argv is executed on the NAS over one persistent SSH connection
(see ``ssh_remote``). The function names keep their historical ``local``
naming because every tool module calls them; "local" means *local to the
NAS*, wherever this process happens to run.
"""

import os
import subprocess

from . import config  # late-bound so setup can inject connection details

# Non-login shells (e.g. `ssh host -- python ...`) get a minimal PATH; make sure
# /usr/sbin (omv-rpc) and /usr/bin (docker) are reachable regardless.
_ENV = {
    **os.environ,
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:"
    + os.environ.get("PATH", ""),
}


def run_local(argv, timeout=60, input_text=None):
    """Run an argv list (no shell) on the NAS; return {stdout, stderr, exit_code}."""
    if config.OMV_HOST:
        from .ssh_remote import run_remote  # lazy: Mode A never touches paramiko

        return run_remote(argv, timeout=timeout, input_text=input_text)
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
