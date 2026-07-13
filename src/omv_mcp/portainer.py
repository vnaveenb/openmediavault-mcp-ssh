"""Portainer REST API wrappers (stacks + a container listing fallback).

Reached locally at http://localhost:9000/api on the NAS. Only used by the stack
tools; requires PORTAINER_API_KEY in the NAS .env.
"""

import requests

from .config import PORTAINER_API_KEY, PORTAINER_ENDPOINT_ID, PORTAINER_URL


def _base_url() -> str:
    """Explicit PORTAINER_URL wins; otherwise the on-NAS default."""
    return PORTAINER_URL or "http://localhost:9000/api"


def _session() -> requests.Session:
    if not PORTAINER_API_KEY:
        raise RuntimeError(
            "PORTAINER_API_KEY is not set. Run `omv-mcp setup` (or add it to "
            "the config.env / .env) to enable the Portainer stack tools."
        )
    s = requests.Session()
    s.headers.update({"X-API-Key": PORTAINER_API_KEY})
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
        params={"endpointId": PORTAINER_ENDPOINT_ID},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


def stop_stack(stack_id: int):
    """Stop a running stack (takes its containers down). 409 if already stopped."""
    r = _session().post(
        f"{_base_url()}/stacks/{stack_id}/stop",
        params={"endpointId": PORTAINER_ENDPOINT_ID},
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
        params={"endpointId": PORTAINER_ENDPOINT_ID},
        json=body,
        timeout=180,
    )
    r.raise_for_status()
    return r.json()
