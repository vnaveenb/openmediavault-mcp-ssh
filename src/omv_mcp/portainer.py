"""Portainer REST API wrappers (stacks + a container listing fallback).

Reached at localhost:9000 in Mode A (on the NAS) or through the SSH tunnel in
Mode B (see tunnel.py); an explicit PORTAINER_URL overrides both. Only used by
the stack tools; requires PORTAINER_API_KEY in the config.
"""

import requests

from . import config  # late-bound so setup can inject the API key


def _base_url() -> str:
    """Explicit PORTAINER_URL wins; else SSH tunnel in Mode B, localhost in Mode A."""
    if config.PORTAINER_URL:
        return config.PORTAINER_URL
    if config.OMV_HOST:
        from .tunnel import tunnel_url  # lazy: starts the forwarder on first use

        return tunnel_url()
    return "http://localhost:9000/api"


def _session() -> requests.Session:
    if not config.PORTAINER_API_KEY:
        raise RuntimeError(
            "PORTAINER_API_KEY is not set. Run `omv-mcp setup` (or add it to "
            "the config.env / .env) to enable the Portainer stack tools."
        )
    s = requests.Session()
    s.headers.update({"X-API-Key": config.PORTAINER_API_KEY})
    return s


def list_stacks():
    r = _session().get(f"{_base_url()}/stacks", timeout=30)
    r.raise_for_status()
    return r.json()


def get_stack(stack_id: int):
    r = _session().get(f"{_base_url()}/stacks/{stack_id}", timeout=30)
    r.raise_for_status()
    return r.json()


def get_stack_file(stack_id: int) -> str:
    r = _session().get(f"{_base_url()}/stacks/{stack_id}/file", timeout=30)
    r.raise_for_status()
    return r.json().get("StackFileContent", "")


def start_stack(stack_id: int):
    """Start a stopped stack. Returns the stack JSON (409 if already running)."""
    r = _session().post(
        f"{_base_url()}/stacks/{stack_id}/start",
        params={"endpointId": config.PORTAINER_ENDPOINT_ID},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


def stop_stack(stack_id: int):
    """Stop a running stack (takes its containers down). 409 if already stopped."""
    r = _session().post(
        f"{_base_url()}/stacks/{stack_id}/stop",
        params={"endpointId": config.PORTAINER_ENDPOINT_ID},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


def update_stack(stack_id: int, compose: str, prune: bool = False, pull_image: bool = False):
    """PUT a modified compose back, preserving the stack's existing Env."""
    s = _session()
    existing = s.get(f"{_base_url()}/stacks/{stack_id}", timeout=30)
    existing.raise_for_status()
    env = existing.json().get("Env", [])
    body = {
        "StackFileContent": compose,
        "Env": env,
        "Prune": prune,
        "PullImage": pull_image,
    }
    r = s.put(
        f"{_base_url()}/stacks/{stack_id}",
        params={"endpointId": config.PORTAINER_ENDPOINT_ID},
        json=body,
        timeout=180,
    )
    r.raise_for_status()
    return r.json()
