"""Entry point. Runs a FastMCP server over stdio.

CRITICAL for stdio-over-SSH: stdout must carry ONLY JSON-RPC. All logging goes
to stderr; nothing here may ``print()`` to stdout.
"""

import logging
import sys

from mcp.server.fastmcp import FastMCP

from .tools import register


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp = FastMCP("omv")
    register(mcp)
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
