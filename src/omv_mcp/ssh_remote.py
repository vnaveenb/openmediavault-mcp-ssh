"""Persistent SSH executor for Mode B (server runs OFF the NAS).

One paramiko ``SSHClient`` per process; each command is a fresh exec channel on
that connection, so we pay the TCP+SSH handshake once per session, not per
call. Auth order: ssh-agent -> explicit key file (``OMV_SSH_KEY``) -> default
``~/.ssh`` keys. Host keys are trust-on-first-use, persisted to
``<config_dir>/known_hosts``; a *changed* key raises loudly (paramiko's
``BadHostKeyException``) instead of connecting.

Commands are argv lists quoted with ``shlex.join`` so the remote side sees the
exact argv ``subprocess.run`` would have — preserving ``run_local``'s no-shell
semantics (the only shell involved is the one sshd always spawns).
"""

import logging
import shlex
import threading
import time

import paramiko

from .config import OMV_HOST, OMV_SSH_KEY, OMV_SSH_PORT, OMV_SSH_USER, config_dir

log = logging.getLogger(__name__)

# Same PATH guarantee local.py makes: sshd gives non-login shells a minimal
# PATH; omv-rpc lives in /usr/sbin, docker in /usr/bin.
_PATH_PREFIX = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

_lock = threading.RLock()
_client: paramiko.SSHClient | None = None


class _TofuPolicy(paramiko.MissingHostKeyPolicy):
    """Trust-on-first-use: persist unseen host keys to our known_hosts file.

    Only fires for *unknown* hosts — a known host presenting a different key
    still raises ``BadHostKeyException`` before this policy is consulted.
    """

    def __init__(self, path):
        self._path = path

    def missing_host_key(self, client, hostname, key):
        log.info("Trusting new host key for %s (%s)", hostname, key.get_name())
        client.get_host_keys().add(hostname, key.get_name(), key)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        client.save_host_keys(str(self._path))


def _connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    known_hosts = config_dir() / "known_hosts"
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(_TofuPolicy(known_hosts))
    client.connect(
        OMV_HOST,
        port=OMV_SSH_PORT,
        username=OMV_SSH_USER,
        key_filename=OMV_SSH_KEY or None,
        allow_agent=True,
        look_for_keys=True,
        timeout=15,
    )
    client.get_transport().set_keepalive(30)
    log.info("SSH connected to %s@%s:%s", OMV_SSH_USER, OMV_HOST, OMV_SSH_PORT)
    return client


def get_client() -> paramiko.SSHClient:
    """The shared connection, (re)established if absent or dead."""
    global _client
    with _lock:
        if _client is not None:
            t = _client.get_transport()
            if t is not None and t.is_active():
                return _client
            try:
                _client.close()
            except Exception:
                pass
            _client = None
        _client = _connect()
        return _client


def _invalidate() -> None:
    global _client
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
            _client = None


def _exec_once(command: str, timeout: float, input_text: str | None) -> dict:
    chan = get_client().get_transport().open_session(timeout=15)
    try:
        chan.settimeout(5)
        chan.exec_command(command)
        if input_text is not None:
            chan.sendall(input_text.encode("utf-8", errors="replace"))
        chan.shutdown_write()

        out, err = bytearray(), bytearray()
        deadline = time.monotonic() + timeout
        while True:
            got = False
            while chan.recv_ready():
                out += chan.recv(65536)
                got = True
            while chan.recv_stderr_ready():
                err += chan.recv_stderr(65536)
                got = True
            if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
                break
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"remote command timed out after {timeout}s: {command[:120]}"
                )
            if not got:
                time.sleep(0.02)
        exit_code = chan.recv_exit_status()
    finally:
        chan.close()
    return {
        "stdout": out.decode("utf-8", errors="replace"),
        "stderr": err.decode("utf-8", errors="replace"),
        "exit_code": exit_code,
    }


def run_remote(argv, timeout=60, input_text=None) -> dict:
    """Run an argv list on the NAS over SSH; same contract as ``run_local``.

    Retries exactly once on a dead/dropped connection (NAS reboot, network
    blip); command/timeout errors are surfaced, not retried.
    """
    command = f"PATH={_PATH_PREFIX}:$PATH " + shlex.join(str(a) for a in argv)
    try:
        return _exec_once(command, timeout, input_text)
    except TimeoutError:
        raise  # the command timed out; do NOT run it a second time
    except (paramiko.SSHException, EOFError, OSError) as e:
        log.warning("SSH exec failed (%s); reconnecting once", e)
        _invalidate()
        return _exec_once(command, timeout, input_text)
