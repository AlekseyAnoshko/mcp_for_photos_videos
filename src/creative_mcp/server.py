"""STDIO baseline. Graphics editing tools will be added as adapters."""
import logging
import platform
import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from .runtime import config_path, probe, read_config

mcp = FastMCP("creative-mcp")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                     idempotentHint=True, openWorldHint=False))
def system_info() -> dict[str, object]:
    """Return configured GIMP 3 and Blender versions without editing files."""
    config = read_config()
    return {
        "python": {"version": platform.python_version(), "path": sys.executable},
        "gimp": probe(config["gimp"]["command"], 3),
        "blender": probe(config["blender"]["command"], 3),
        "workspace": config["workspace"],
        "config": str(config_path()),
        "capabilities": ["system_info"],
    }


def main():
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    read_config()  # Fail before transport startup if configuration is invalid.
    mcp.run(transport="stdio")
