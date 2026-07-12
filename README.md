# omv-mcp — MCP server for the OpenMediaVault NAS

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-%E2%89%A53.12-blue?logo=python&logoColor=white">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-1.28%2B-6E56CF?logo=modelcontextprotocol&logoColor=white">
  <img alt="Built with uv" src="https://img.shields.io/badge/built%20with-uv-DE5FE9?logo=astral&logoColor=white">
  <img alt="Platform" src="https://img.shields.io/badge/platform-OpenMediaVault%20(Debian%2011)-5AC8FA?logo=debian&logoColor=white">
  <a href="CONTRIBUTING.md"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg"></a>
  <img alt="Maintained" src="https://img.shields.io/badge/maintained-yes-brightgreen.svg">
</p>

Exposes tools to manage/inspect an OpenMediaVault NAS to any MCP-capable coding
harness (Claude Code, Copilot, Codex, …).

> Throughout this README, `<nas-ip>` is your NAS host/IP and `/opt/omv-mcp` is
> wherever you deploy this project on the NAS — substitute your own values.

## Architecture

- **Runs ON the NAS** (Debian 11), not on your workstation. Every tool is a
  *local* subprocess call to `omv-rpc` / `docker` / `df` / `lsblk` — no per-call
  SSH. This sidesteps the official `openmediavault-mcp`, which drives OMV over
  HTTP `/rpc.php` with the web-admin password (a credential we don't have).
- **Transport: stdio over one SSH pipe.** Each client launches the server as an
  `ssh … python -m omv_mcp` command; SSH carries JSON-RPC over a single
  connection per session. No listening port, no new auth — it reuses the
  existing passwordless SSH trust boundary.

```
workstation harness ──(spawns)──▶ ssh root@<nas-ip> -T -- <venv python> -m omv_mcp
                                            │ (runs on the NAS)
                                            ├─ omv-rpc -u admin …   (local, no password)
                                            ├─ docker …             (local)
                                            └─ Portainer @ localhost:9000
```

## ⚠️ Safety

This server runs as **root** and is meant for a single trusted user on a home
LAN. There is **no deny-list**. `run_command` and `omv_rpc` are **unrestricted
root** — they can do anything. The only guarded tools are the obviously
destructive named ones (`reboot`, `shutdown`, `update_stack`), which require
`confirm=True`. Do not expose this server to untrusted clients.

## Install (on the NAS)

Source of truth is authored on the workstation and `scp`-deployed to
`/opt/omv-mcp`. Then, on the NAS:

```bash
cd /opt/omv-mcp
cp .env.example .env          # then paste the real PORTAINER_API_KEY into .env
uv sync                       # builds .venv with Python 3.12 + deps
```

`uv` fetches a standalone CPython 3.12 (system `python3` is 3.9, too old for the
`mcp` SDK). The real `.env` lives **only on the NAS** and is never committed/scp'd.

## Register with a client

Point the client at the venv interpreter over SSH (launch it directly, not via
`uv run`, so nothing pollutes stdout):

```bash
claude mcp add omv -- ssh root@<nas-ip> -T -- \
  /opt/omv-mcp/.venv/bin/python -m omv_mcp
```

Equivalent `.mcp.json` / Claude Desktop config:

```json
{
  "mcpServers": {
    "omv": {
      "command": "ssh",
      "args": [
        "root@<nas-ip>", "-T", "--",
        "/opt/omv-mcp/.venv/bin/python", "-m", "omv_mcp"
      ]
    }
  }
}
```

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

## Prompts

Canned diagnostic workflows: `diagnose_storage_health`, `triage_containers`,
`whats_using_space`, `audit_shares_and_permissions`.

## Completions

Argument autocompletion (spec-correct: for prompt/resource-template args, not
tool inputs): container names for `omv://container/{name}/logs`, stack ids for
`omv://stack/{stack_id}/compose`, and shared-folder names for the
`audit_shares_and_permissions` prompt's `share` argument.

## Long-running tools & progress

`apply_updates`, `docker_prune`, `stop_stack`, `restart_stack`, and
`update_stack` are async and emit MCP log/progress notifications while they run.

## Smoke test (on the NAS)

```bash
uv run python tests/smoke_client.py
```

Spawns the server over stdio, lists tools, and calls a few read-only ones
against live data.

## Contributing

**PRs welcome!** 🎉 Whether it's a new tool, a bug fix, or docs — contributions
are appreciated. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

Quick start:

```bash
git clone https://github.com/vnaveenb/openmediavault-mcp-ssh.git
cd openmediavault-mcp-ssh/omv-mcp
uv sync                                  # build .venv (Python 3.12 + deps)
uv run python tests/smoke_client.py      # sanity-check against a live NAS
```

> ⚠️ This server runs as **root** on the NAS. Review every change with that in
> mind — never merge a PR you haven't read and understood.

### Branching strategy

We follow **[GitHub Flow](https://docs.github.com/en/get-started/quickstart/github-flow)** —
lightweight and PR-driven:

1. `main` is always deployable. Never commit directly to it.
2. Branch off `main` with a descriptive, prefixed name:

   | Prefix | Use for |
   |---|---|
   | `feat/…`  | new tools, resources, or features |
   | `fix/…`   | bug fixes |
   | `docs/…`  | documentation only |
   | `chore/…` | tooling, deps, refactors |

   e.g. `feat/smart-selftest-schedule`, `fix/portainer-timeout`.
3. Commit in small, focused steps ([Conventional Commits](https://www.conventionalcommits.org/)
   encouraged: `feat: …`, `fix: …`, `docs: …`).
4. Open a PR into `main`, fill out the template, and link any related issue.
5. After review, **squash-merge** and delete the branch. Keep `main` linear.

## License

[MIT](LICENSE) © 2026 Naveen Busiraju.
