"""MCP prompts: canned diagnostic workflows.

Each returns an instruction string that steers the client to call the right
tools in the right order and summarise the result. Prompts do not run the tools
themselves — they orchestrate the model that has them.
"""

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.prompt(title="Diagnose storage health")
    def diagnose_storage_health() -> str:
        return (
            "Diagnose the NAS storage health. Steps:\n"
            "1. Call `storage_summary` and flag any mount over 85% used.\n"
            "2. Call `list_disks` to get physical devices, then `smart_health` and "
            "`smart_attributes` for each; flag any device not PASSED, or with a "
            "non-zero Reallocated_Sector_Ct / Current_Pending_Sector / when_failed.\n"
            "3. Call `disk_temperatures` and `cpu_temp`; flag disks over 50°C.\n"
            "Summarise overall health, then list concrete risks and recommended "
            "actions, most urgent first. Do not run any destructive tool."
        )

    @mcp.prompt(title="Triage containers")
    def triage_containers() -> str:
        return (
            "Triage the Docker containers. Steps:\n"
            "1. Call `list_containers` (include_all=True) and identify any that are "
            "exited, restarting, or unhealthy.\n"
            "2. For each problem container, call `container_logs` (tail=80) and "
            "summarise the likely cause.\n"
            "3. Call `container_stats` and flag any container pinning CPU or memory.\n"
            "Report a short status table, then the failing containers with root-cause "
            "guesses and a suggested fix. Only restart a container if I confirm."
        )

    @mcp.prompt(title="What's using my space")
    def whats_using_space() -> str:
        return (
            "Find what is using disk space on the NAS. Steps:\n"
            "1. Call `storage_summary` for per-mount usage.\n"
            "2. Call `docker_system_df` and report reclaimable image/volume/build-cache "
            "space.\n"
            "3. Suggest the biggest safe wins. If Docker has significant reclaimable "
            "space, recommend `docker_prune` (note it needs confirm=True) but do not "
            "run it without my go-ahead."
        )

    @mcp.prompt(title="Audit shares and permissions")
    def audit_shares_and_permissions(share: str = "") -> str:
        scope = f" Focus on the share named '{share}'." if share else ""
        return (
            "Audit the NAS shared folders and SMB exposure." + scope + "\n"
            "1. Call `list_shared_folders` and `list_smb_shares`.\n"
            "2. Cross-reference: flag shared folders with no SMB share, SMB shares "
            "pointing at a missing folder, and any share allowing guest/anonymous "
            "access.\n"
            "3. Summarise the exposure and recommend tightening steps. Do not change "
            "any configuration."
        )
