"""Runtime config. The only real secret is the Portainer API key.

The ``.env`` lives next to the project root on the NAS
(``/opt/omv-mcp/.env``) and is loaded explicitly, because
the server is usually launched with cwd=/root (``ssh ... python -m omv_mcp``),
so a plain ``load_dotenv()`` (cwd-relative) would miss it.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# .../omv-mcp/src/omv_mcp/config.py -> parents[2] == .../omv-mcp
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)
load_dotenv(override=False)  # cwd fallback, if any

PORTAINER_URL = os.environ.get("PORTAINER_URL", "http://localhost:9000/api").rstrip("/")
PORTAINER_API_KEY = os.environ.get("PORTAINER_API_KEY", "")
PORTAINER_ENDPOINT_ID = int(os.environ.get("PORTAINER_ENDPOINT_ID", "1"))
