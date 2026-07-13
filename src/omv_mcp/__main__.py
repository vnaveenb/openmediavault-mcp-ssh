"""Entry point. Bare ``omv-mcp`` runs the FastMCP server over stdio;
``omv-mcp setup`` runs the interactive onboarding.

CRITICAL for the serve path: stdout must carry ONLY JSON-RPC. All logging goes
to stderr; nothing on that path may ``print()`` to stdout. (The setup path is
a normal CLI and prints freely.)
"""

import argparse
import logging
import sys
from importlib.metadata import PackageNotFoundError, version


def _version() -> str:
    try:
        return version("omv-mcp")
    except PackageNotFoundError:  # running from a raw source tree
        return "0.0.0-dev"


def serve() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from mcp.server.fastmcp import FastMCP

    from .tools import register

    mcp = FastMCP("omv")
    register(mcp)
    mcp.run()  # stdio transport by default


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="omv-mcp",
        description="MCP server for OpenMediaVault. No arguments: run the "
        "server (stdio). `setup`: interactive onboarding.",
    )
    parser.add_argument("--version", action="version", version=f"omv-mcp {_version()}")
    sub = parser.add_subparsers(dest="cmd")
    setup_p = sub.add_parser(
        "setup", help="connect this machine to your OMV NAS and register MCP clients"
    )
    setup_p.add_argument(
        "--dev", action="store_true", help=argparse.SUPPRESS
    )  # register the current interpreter instead of `uvx omv-mcp`
    args = parser.parse_args()

    if args.cmd == "setup":
        from .setup_cli import run_setup

        try:
            run_setup(dev=args.dev)
        except KeyboardInterrupt:
            print("\nsetup aborted.")
            sys.exit(130)
        return
    serve()


if __name__ == "__main__":
    main()
