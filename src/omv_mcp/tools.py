"""Top-level registrar. Delegates to per-domain modules so no single file grows
unwieldy. ``__main__`` calls this one ``register(mcp)``.

Grouped: system+maintenance, storage+health, docker, portainer stacks,
users/config. Resources, prompts, and completions are registered here too.

Safety posture (deliberate): this server runs as root on a single-user home NAS
behind an SSH trust boundary. There is NO deny-list. ``run_command`` and
``omv_rpc`` are UNRESTRICTED root. Genuinely destructive *named* tools
(``reboot``, ``shutdown``, ``update_stack``, ``docker_prune``, ``stop_*`` …)
require ``confirm=True`` and carry a destructiveHint annotation.
"""

from mcp.server.fastmcp import FastMCP

from . import (
    completions,
    prompts,
    resources,
    tools_config,
    tools_docker,
    tools_stacks,
    tools_storage,
    tools_system,
)


def register(mcp: FastMCP) -> None:
    tools_system.register(mcp)
    tools_storage.register(mcp)
    tools_docker.register(mcp)
    tools_stacks.register(mcp)
    tools_config.register(mcp)
    resources.register(mcp)
    prompts.register(mcp)
    completions.register(mcp)
