# Contributing to omv-mcp

Thanks for your interest — **PRs are welcome!** This guide covers how to set up,
make changes, and open a pull request.

> ⚠️ **Safety first.** This server runs as **root** on the NAS and has
> unrestricted tools (`run_command`, `omv_rpc`). Treat every change as
> security-sensitive. Never merge a PR you haven't fully read.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (manages Python 3.12 + deps)
- An OpenMediaVault NAS (Debian 11) for live testing, reachable over
  passwordless SSH — optional but recommended for the smoke test.

## Setup

```bash
git clone https://github.com/vnaveenb/openmediavault-mcp-ssh.git
cd openmediavault-mcp-ssh/omv-mcp
uv sync                                  # creates .venv with Python 3.12 + deps
```

Copy the env template if you're testing Portainer tools:

```bash
cp .env.example .env    # paste your real PORTAINER_API_KEY (never commit .env)
```

## Running the smoke test

```bash
uv run python tests/smoke_client.py
```

This spawns the server over stdio, lists tools, and calls a few read-only tools
against live data. Run it before and after your change.

## Branching strategy (GitHub Flow)

1. `main` is always deployable — never commit directly to it.
2. Branch off `main` with a prefixed name:

   | Prefix    | Use for                              |
   |-----------|--------------------------------------|
   | `feat/…`  | new tools, resources, or features    |
   | `fix/…`   | bug fixes                            |
   | `docs/…`  | documentation only                   |
   | `chore/…` | tooling, deps, refactors             |

   Examples: `feat/smart-selftest-schedule`, `fix/portainer-timeout`.
3. Keep commits small and focused. [Conventional Commits](https://www.conventionalcommits.org/)
   are encouraged: `feat: …`, `fix: …`, `docs: …`, `chore: …`.
4. Open a PR into `main`, fill out the template, and link any related issue.
5. After review, we **squash-merge** and delete the branch to keep `main` linear.

## Adding a new tool

- Put it in the relevant `tools_*.py` module (`tools_system.py`,
  `tools_docker.py`, `tools_stacks.py`, `tools_storage.py`, `tools_config.py`).
- Prefer local subprocess calls (`omv-rpc`, `docker`, `df`, …) — no per-call SSH.
- Any **destructive** tool must require `confirm=True` and be marked ⚠️ in the
  README Tools table.
- Update the **Tools** table in [README.md](README.md).

## PR checklist

- [ ] Smoke test passes (or explain why it can't run in your setup).
- [ ] README updated if tools/resources/prompts changed.
- [ ] Destructive actions guarded with `confirm=True`.
- [ ] No secrets committed (`.env`, API keys, host IPs).

## Reporting issues

Open an issue describing the NAS/OMV version, the tool involved, expected vs.
actual behavior, and any relevant logs (with secrets redacted).
