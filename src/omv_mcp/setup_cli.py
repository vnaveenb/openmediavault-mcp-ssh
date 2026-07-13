"""Interactive onboarding: ``uvx omv-mcp setup``.

Flow: collect connection details -> ensure passwordless SSH (installing the
user's public key with their password, used exactly once, never stored) ->
LIVE-verify through the same executor prod uses -> optional Portainer key ->
choose mode -> register with the MCP client.

Everything here may print to stdout freely — this is the CLI, not the server.
"""

import getpass
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import paramiko

from . import config
from .ssh_remote import _TofuPolicy

_DEFAULT_KEY_NAMES = ["id_ed25519", "id_ecdsa", "id_rsa"]


# --------------------------------------------------------------------------
# small console helpers
# --------------------------------------------------------------------------

def _say(msg: str) -> None:
    print(msg)


def _ok(msg: str) -> None:
    print(f"  [ok] {msg}")


def _fail(msg: str) -> None:
    print(f"  [!!] {msg}")


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default


# --------------------------------------------------------------------------
# SSH key discovery / generation (workstation side)
# --------------------------------------------------------------------------

def find_or_create_key() -> tuple[Path, str]:
    """Return (private_key_path, public_key_line), generating ed25519 if none."""
    ssh_dir = Path.home() / ".ssh"
    for name in _DEFAULT_KEY_NAMES:
        priv, pub = ssh_dir / name, ssh_dir / f"{name}.pub"
        if priv.exists() and pub.exists():
            _ok(f"using existing SSH key {priv}")
            return priv, pub.read_text().strip()

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    priv_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    )
    pub_line = (
        key.public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode()
        + " omv-mcp"
    )
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    priv = ssh_dir / "id_ed25519"
    priv.write_bytes(priv_bytes)
    (ssh_dir / "id_ed25519.pub").write_text(pub_line + "\n")
    if sys.platform != "win32":
        priv.chmod(0o600)
    _ok(f"generated new SSH key {priv}")
    return priv, pub_line


# --------------------------------------------------------------------------
# bootstrap connection (key first, password once as fallback)
# --------------------------------------------------------------------------

def _connect(password: str | None = None) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    known_hosts = config.config_dir() / "known_hosts"
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(_TofuPolicy(known_hosts))
    client.connect(
        config.OMV_HOST,
        port=config.OMV_SSH_PORT,
        username=config.OMV_SSH_USER,
        password=password,
        allow_agent=password is None,
        look_for_keys=password is None,
        timeout=15,
    )
    return client


def _exec(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out, err


def ensure_passwordless_ssh() -> paramiko.SSHClient:
    """Return an authenticated client, installing our public key if needed."""
    target = f"{config.OMV_SSH_USER}@{config.OMV_HOST}:{config.OMV_SSH_PORT}"
    try:
        client = _connect()
        _ok(f"passwordless SSH to {target} already works")
        return client
    except paramiko.AuthenticationException:
        pass  # expected on first run — fall through to password bootstrap

    _priv, pub = find_or_create_key()
    _say(f"\n  Key-based login not set up yet. Your OMV password is needed ONCE\n"
         f"  to install the key; it is never stored.")
    for attempt in range(3):
        pw = getpass.getpass(f"  password for {target}: ")
        try:
            client = _connect(password=pw)
            break
        except paramiko.AuthenticationException:
            _fail("authentication failed" + (", try again" if attempt < 2 else ""))
    else:
        raise SystemExit("Could not authenticate with the OMV password.")

    qpub = shlex.quote(pub)
    code, _out, err = _exec(
        client,
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        f"grep -qxF {qpub} ~/.ssh/authorized_keys 2>/dev/null || "
        f"printf '%s\\n' {qpub} >> ~/.ssh/authorized_keys; "
        "chmod 600 ~/.ssh/authorized_keys",
    )
    if code != 0:
        raise SystemExit(f"Failed to install SSH key on the NAS: {err.strip()}")
    client.close()

    # prove the key works before moving on
    try:
        client = _connect()
    except paramiko.AuthenticationException as e:
        raise SystemExit(f"Key installed but key-login still fails: {e}")
    _ok("public key installed — passwordless SSH verified")
    return client


# --------------------------------------------------------------------------
# live verification through the REAL executor (local.py -> ssh_remote.py)
# --------------------------------------------------------------------------

def live_verify() -> None:
    from .local import run_local

    r = run_local(["/usr/sbin/omv-rpc", "-u", "admin", "System", "getInformation"],
                  timeout=30)
    if r["exit_code"] != 0:
        raise SystemExit(
            f"omv-rpc failed on the NAS (is this an OpenMediaVault host? "
            f"is the user root?): {r['stderr'].strip()}"
        )
    import json

    info = json.loads(r["stdout"])
    _ok(f"OMV {info.get('version', '?')} on {info.get('hostname', '?')}")

    r = run_local(["docker", "ps", "-q"], timeout=30)
    if r["exit_code"] == 0:
        _ok(f"docker reachable — {len(r['stdout'].split())} running containers")
    else:
        _fail(f"docker not reachable ({r['stderr'].strip()[:80]}) — "
              "container tools will not work")


def verify_portainer() -> bool:
    from .portainer import list_stacks

    try:
        stacks = list_stacks()
        _ok(f"Portainer reachable — {len(stacks)} stacks")
        return True
    except Exception as e:
        _fail(f"Portainer check failed: {e}")
        return False


# --------------------------------------------------------------------------
# config writing
# --------------------------------------------------------------------------

def write_config_env(values: dict, header: str) -> Path:
    path = config.CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {header}"]
    lines += [f"{k}={v}" for k, v in values.items() if v not in ("", None)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if sys.platform != "win32":
        path.chmod(0o600)
    _ok(f"wrote {path}")
    return path


# --------------------------------------------------------------------------
# Mode A: deploy onto the NAS (advanced)
# --------------------------------------------------------------------------

def deploy_on_nas(client: paramiko.SSHClient, portainer_key: str) -> str:
    """Install uv + config on the NAS; return the remote uvx path."""
    _say("  ensuring uv on the NAS ...")
    code, out, _err = _exec(client, "command -v uvx || ls ~/.local/bin/uvx 2>/dev/null")
    if code != 0:
        code, _out, err = _exec(
            client, "curl -LsSf https://astral.sh/uv/install.sh | sh", timeout=300
        )
        if code != 0:
            raise SystemExit(f"Failed to install uv on the NAS: {err.strip()}")
        code, out, _err = _exec(client, "ls ~/.local/bin/uvx")
        if code != 0:
            raise SystemExit("uv installed but uvx not found at ~/.local/bin/uvx")
    uvx_path = out.strip().splitlines()[0]
    _ok(f"uvx on NAS: {uvx_path}")

    lines = ["# written by `omv-mcp setup` (Mode A: server runs on this NAS)"]
    if portainer_key:
        lines.append(f"PORTAINER_API_KEY={portainer_key}")
    body = "\n".join(lines) + "\n"
    chan = client.get_transport().open_session()
    chan.exec_command("mkdir -p ~/.config/omv-mcp && cat > ~/.config/omv-mcp/config.env "
                      "&& chmod 600 ~/.config/omv-mcp/config.env")
    chan.sendall(body.encode())
    chan.shutdown_write()
    if chan.recv_exit_status() != 0:
        raise SystemExit("Failed to write config.env on the NAS")
    chan.close()
    _ok("wrote ~/.config/omv-mcp/config.env on the NAS")

    _say("  pre-warming uvx cache on the NAS (first run downloads Python 3.12) ...")
    code, out, err = _exec(client, f"{uvx_path} omv-mcp --version", timeout=600)
    if code == 0:
        _ok(f"NAS can run: omv-mcp {out.strip()}")
    else:
        _fail(f"pre-warm failed ({err.strip()[:100]}) — first client connect "
              "will be slow or fail until `uvx omv-mcp` resolves")
    return uvx_path


# --------------------------------------------------------------------------
# client registration
# --------------------------------------------------------------------------

def _server_command(mode: str, uvx_on_nas: str, dev: bool) -> list[str]:
    if mode == "A":
        return [
            "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-p", str(config.OMV_SSH_PORT),
            f"{config.OMV_SSH_USER}@{config.OMV_HOST}", "-T", "--",
            uvx_on_nas, "omv-mcp",
        ]
    if dev:  # source checkout: use this exact interpreter/venv
        return [sys.executable, "-m", "omv_mcp"]
    return ["uvx", "omv-mcp"]


def register_clients(command: list[str]) -> None:
    exe, args = command[0], command[1:]

    claude = shutil.which("claude")
    if claude:
        add = [claude, "mcp", "add", "omv", "--", exe, *args]
        res = subprocess.run(add, capture_output=True, text=True)
        if res.returncode != 0 and "already exists" in (res.stdout + res.stderr):
            subprocess.run([claude, "mcp", "remove", "omv"], capture_output=True, text=True)
            res = subprocess.run(add, capture_output=True, text=True)
        if res.returncode == 0:
            _ok("registered with Claude Code (`claude mcp list` to confirm)")
        else:
            _fail(f"claude mcp add failed: {(res.stderr or res.stdout).strip()[:200]}")
    else:
        _say("  Claude Code CLI not found — register manually:")
        _say(f"    claude mcp add omv -- {' '.join(command)}")

    import json

    block = json.dumps({"omv": {"command": exe, "args": args}}, indent=2)
    vscode_block = json.dumps(
        {"servers": {"omv": {"type": "stdio", "command": exe, "args": args}}}, indent=2
    )
    _say(f"""
  For other MCP clients, paste this server entry:

  Claude Desktop  (Settings > Developer > Edit Config,
                   claude_desktop_config.json -> "mcpServers"):
{block}

  VS Code  (.vscode/mcp.json):
{vscode_block}

  Cursor  (~/.cursor/mcp.json -> "mcpServers"): same entry as Claude Desktop.
""")


# --------------------------------------------------------------------------
# main flow
# --------------------------------------------------------------------------

def run_setup(dev: bool = False) -> None:
    _say("\nomv-mcp setup — connect this machine to your OpenMediaVault NAS\n")

    config.OMV_HOST = _ask("  OMV host or IP (LAN IP like 192.168.x.x; Tailscale IPs "
                           "usually work too)", config.OMV_HOST)
    if not config.OMV_HOST:
        raise SystemExit("A host is required.")
    config.OMV_SSH_USER = _ask("  SSH user (v1 requires root)", config.OMV_SSH_USER)
    config.OMV_SSH_PORT = int(_ask("  SSH port", str(config.OMV_SSH_PORT)))

    _say("")
    client = ensure_passwordless_ssh()

    _say("\n  Verifying the NAS ...")
    live_verify()

    _say("\n  Portainer API key enables the stack tools (list/start/stop/update\n"
         "  compose stacks). Portainer > user icon > 'Access tokens' > Add.")
    portainer_key = _ask("  Portainer API key (blank to skip)", "")
    if portainer_key:
        config.PORTAINER_API_KEY = portainer_key
        verify_portainer()

    _say("\n  Where should the MCP server run?\n"
         "    [B] Here on this machine, reaching the NAS over SSH (recommended)\n"
         "    [A] On the NAS itself (advanced; client connects via ssh)")
    mode = _ask("  mode", "B").strip().upper()

    uvx_on_nas = ""
    if mode == "A":
        uvx_on_nas = deploy_on_nas(client, portainer_key)
    else:
        mode = "B"
        write_config_env(
            {
                "OMV_HOST": config.OMV_HOST,
                "OMV_SSH_USER": config.OMV_SSH_USER,
                "OMV_SSH_PORT": config.OMV_SSH_PORT,
                "PORTAINER_API_KEY": portainer_key,
            },
            header="written by `omv-mcp setup` (Mode B: server runs on this machine)",
        )

    client.close()

    _say("\n  Registering with MCP clients ...")
    register_clients(_server_command(mode, uvx_on_nas, dev))

    _say("  Done. Ask your AI client something like: \"what's the health of my NAS?\"\n")
