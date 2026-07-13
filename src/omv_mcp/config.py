"""Runtime config for both modes.

Load order (first hit wins per key — ``override=False`` all the way down):

1. Real environment variables.
2. Per-user config file written by ``omv-mcp setup``:
   - Windows:  ``%APPDATA%\\omv-mcp\\config.env``
   - elsewhere: ``$XDG_CONFIG_HOME/omv-mcp/config.env`` (default ``~/.config/...``)
3. Legacy project-root ``.env`` (source checkouts deployed on the NAS) and a
   cwd ``.env`` fallback — kept for Mode-A back-compat.

Mode selection: ``OMV_HOST`` set -> Mode B (this process runs anywhere and
reaches the NAS over SSH). Unset -> Mode A (this process runs ON the NAS and
execs locally).
"""

import os
from pathlib import Path

from dotenv import load_dotenv


def config_dir() -> Path:
    """Per-user omv-mcp config directory (config.env, known_hosts)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "omv-mcp"


CONFIG_FILE = config_dir() / "config.env"
load_dotenv(CONFIG_FILE, override=False)

# Legacy fallbacks: .env next to a source checkout (harmless no-op when
# installed as a wheel), then a cwd .env if any.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(override=False)

# --- connection (Mode B only; empty OMV_HOST means Mode A / on-NAS) ---------
OMV_HOST = os.environ.get("OMV_HOST", "").strip()
OMV_SSH_USER = os.environ.get("OMV_SSH_USER", "root").strip() or "root"
OMV_SSH_PORT = int(os.environ.get("OMV_SSH_PORT", "22"))
OMV_SSH_KEY = os.environ.get("OMV_SSH_KEY", "").strip()  # explicit private-key path

# --- Portainer ---------------------------------------------------------------
# PORTAINER_URL empty means "auto": localhost in Mode A, SSH tunnel in Mode B
# (resolved lazily in portainer.py). An explicit value always wins.
PORTAINER_URL = os.environ.get("PORTAINER_URL", "").rstrip("/")
PORTAINER_API_KEY = os.environ.get("PORTAINER_API_KEY", "")
PORTAINER_ENDPOINT_ID = int(os.environ.get("PORTAINER_ENDPOINT_ID", "1"))
