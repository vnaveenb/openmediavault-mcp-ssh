# omv-mcp — MCP server for the OpenMediaVault NAS

<p align="center">
  <a href="https://pypi.org/project/omv-mcp/"><img alt="PyPI" src="https://img.shields.io/pypi/v/omv-mcp?color=3775A9&logo=pypi&logoColor=white"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-%E2%89%A53.12-blue?logo=python&logoColor=white">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-1.28%2B-6E56CF?logo=modelcontextprotocol&logoColor=white">
  <img alt="Built with uv" src="https://img.shields.io/badge/built%20with-uv-DE5FE9?logo=astral&logoColor=white">
  <img alt="Platform" src="https://img.shields.io/badge/NAS-OpenMediaVault%20(Debian%2011%2B)-5AC8FA?logo=debian&logoColor=white">
  <a href="CONTRIBUTING.md"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg"></a>
</p>

Manage and inspect an OpenMediaVault NAS from any MCP-capable AI harness
(Claude Code, Claude Desktop, Copilot, Cursor, Codex, …): 48 tools across
system, storage/SMART health, Docker, and Portainer stacks, plus resources,
prompts, and completions.

## Install (one command)

Install [uv](https://docs.astral.sh/uv/) if you don't have it, then run setup:

```powershell
# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
uvx omv-mcp setup
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
uvx omv-mcp setup
```

Setup asks for your NAS address and SSH login, then does everything else:

1. **Passwordless SSH** — if key login isn't set up yet, it installs your
   public key using your OMV password **once** (never stored; an ed25519 key
   is generated if you don't have one).
2. **Live verification** — runs real `omv-rpc` and `docker ps` on the NAS and
   shows the results.
3. **Portainer (optional)** — paste an API key to enable the compose-stack
   tools (Portainer → user icon → *Access tokens*); blank to skip.
4. **Registration** — registers with Claude Code automatically and prints
   paste-ready config blocks for Claude Desktop, VS Code, and Cursor.

> **Requirements:** root SSH login on the NAS (OMV's default) and any address
> that reaches it — a LAN IP like `192.168.x.x` is what v1 is tested on.
> Tailscale IPs usually work as-is; official Tailscale support lands in v2.

## Two modes, one package

**Mode B — run anywhere (default).** The server runs on *your* machine and
executes every command on the NAS over **one persistent SSH connection**
(~25 ms per call after the handshake). Nothing is installed on the NAS.

```
your machine                                 NAS (OMV, Debian)
┌────────────────────────────┐               ┌──────────────────────┐
│ MCP client ──▶ omv-mcp     │ ═ ssh (1) ══▶ │ omv-rpc / docker / … │
│              (uvx omv-mcp) │ ─ tunnel ───▶ │ Portainer :9000      │
└────────────────────────────┘               └──────────────────────┘
```

**Mode A — run on the NAS (advanced).** Choose `A` during setup: it installs
uv on the NAS and registers the client to launch the server *there* over
stdio-on-SSH. Commands are then local subprocess calls on the NAS.

```
your machine                        NAS (OMV, Debian)
┌─────────────┐                     ┌────────────────────────────────┐
│ MCP client ─┼── ssh … uvx omv-mcp ▶ omv-mcp ─▶ omv-rpc / docker / …│
└─────────────┘                     └────────────────────────────────┘
```

The selector is one config key: `OMV_HOST` set → Mode B; unset → Mode A.

## Configuration

`omv-mcp setup` writes this for you. File location:
`%APPDATA%\omv-mcp\config.env` (Windows) or `~/.config/omv-mcp/config.env`
(macOS/Linux/NAS). Real environment variables override the file.

| Key | Default | Meaning |
|---|---|---|
| `OMV_HOST` | *(empty)* | NAS address. Set = Mode B (remote); empty = Mode A (on-NAS). |
| `OMV_SSH_USER` | `root` | SSH user (v1 requires root). |
| `OMV_SSH_PORT` | `22` | SSH port. |
| `OMV_SSH_KEY` | *(empty)* | Explicit private key path; default is ssh-agent, then `~/.ssh` keys. |
| `PORTAINER_URL` | *(auto)* | Explicit Portainer API URL. Auto = `localhost:9000` in Mode A, SSH tunnel in Mode B. |
| `PORTAINER_API_KEY` | *(empty)* | Enables the stack tools. |
| `PORTAINER_ENDPOINT_ID` | `1` | Portainer endpoint id. |

Host keys are trust-on-first-use, pinned in `<config dir>/known_hosts`; a
changed host key fails loudly. Dropped SSH connections reconnect once,
transparently. In Mode B, Portainer traffic rides an SSH tunnel — the API key
never crosses your network in cleartext, and no port besides SSH needs to be
reachable.

## Register a client manually

Setup prints these for you; for reference (Mode B):

```json
{ "mcpServers": { "omv": { "command": "uvx", "args": ["omv-mcp"] } } }
```

```bash
claude mcp add omv -- uvx omv-mcp
```

VS Code (`.vscode/mcp.json`) uses `"servers"` with `"type": "stdio"`, same
command. For Mode A, setup prints the equivalent `ssh …@nas -T -- uvx omv-mcp`
form.

**Updating:** `uvx` caches the package; refresh with `uvx omv-mcp@latest --version`
(or `uv cache clean omv-mcp`).

## ⚠️ Safety

This server executes as **root on the NAS** and is meant for a single trusted
user. There is **no deny-list** — `run_command` and `omv_rpc` are unrestricted
root. The destructive named tools (`reboot`, `shutdown`, `apply_updates`,
`docker_prune`, `stop_container`, `stop_stack`, `restart_stack`,
`update_stack`, `run_smart_test`) require `confirm=True`. Your Portainer API
key is stored in the per-user config file on whichever machine runs the
server. Do not expose this server to untrusted clients.

## Tools

| Group | Tools |
|---|---|
| System | `get_system_info`, `disk_usage`, `list_block_devices`, `top_processes`, `memory_info`, `network_info`, `service_status`, `service_logs`, `available_updates`, `apply_updates` ⚠️, `run_command` ⚠️, `reboot` ⚠️, `shutdown` ⚠️ |
| Storage / health | `list_filesystems`, `list_disks`, `storage_summary`, `smart_status`, `smart_health`, `smart_attributes`, `smart_selftest_log`, `run_smart_test` ⚠️, `disk_temperatures`, `cpu_temp`, `sensors_readout`, `list_shared_folders`, `list_smb_shares`, `omv_rpc` ⚠️ |
| Users/groups | `list_users`, `list_groups` |
| Docker | `list_containers`, `container_stats`, `container_inspect`, `container_logs`, `list_images`, `list_volumes`, `list_networks`, `docker_system_df`, `start_container`, `restart_container`, `stop_container` ⚠️, `docker_exec` ⚠️, `docker_prune` ⚠️ |
| Portainer stacks | `list_stacks`, `get_stack_compose`, `start_stack`, `stop_stack` ⚠️, `restart_stack` ⚠️, `update_stack` ⚠️ |

⚠️ = unrestricted root or requires `confirm=True`.

## Resources

Read-only NAS context any client can pull without a tool call:

| URI | Content |
|---|---|
| `omv://system` | live host/OMV info (JSON) |
| `omv://storage/overview` | per-mount usage for OS + data disks (JSON) |
| `omv://health` | composite: SMART overall + disk/CPU temps + df (JSON) |
| `omv://stacks` | Portainer stacks (JSON) |
| `omv://container/{name}/logs` | last 100 log lines (template) |
| `omv://stack/{stack_id}/compose` | compose YAML (template) |

## Prompts & completions

Canned diagnostic workflows — `diagnose_storage_health`, `triage_containers`,
`whats_using_space`, `audit_shares_and_permissions` — plus argument
autocompletion for container names, stack ids, and share names.

`apply_updates`, `docker_prune`, `stop_stack`, `restart_stack`, and
`update_stack` are async and emit MCP log/progress notifications while they run.

## Development

```bash
git clone https://github.com/vnaveenb/openmediavault-mcp-ssh.git
cd openmediavault-mcp-ssh
uv sync                                  # venv with Python 3.12 + deps
uv run pytest                            # unit tests (no NAS needed)
uv run python tests/smoke_client.py      # live smoke test (uses your config.env)
uv run omv-mcp setup --dev               # register THIS checkout instead of PyPI
```

**PRs welcome!** See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow
(GitHub Flow, conventional commits, squash-merge).

> ⚠️ This server runs as **root** on the NAS. Review every change with that in
> mind — never merge a PR you haven't read and understood.

## License

[MIT](LICENSE) © 2026 Naveen Busiraju.
