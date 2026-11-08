"""One MCP connection; run with the installed virtual environment's Python."""
import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    executable = Path(sys.executable).parent / ("creative-mcp.exe" if sys.platform == "win32" else "creative-mcp")
    async with asyncio.timeout(60):
        async with stdio_client(StdioServerParameters(command=str(executable), env=dict(os.environ))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                assert "system_info" in {tool.name for tool in listing.tools}
                result = await session.call_tool("system_info", {})
                assert not result.isError, result
                data = result.structuredContent
                if data is None:
                    data = json.loads("\n".join(block.text for block in result.content if block.type == "text"))
                assert {"gimp", "blender", "python"} <= data.keys(), data
                print(json.dumps(data, ensure_ascii=False, indent=2))
                assert data["gimp"]["available"] and data["blender"]["available"], "Приложения не готовы; см. результат выше"


if __name__ == "__main__":
    asyncio.run(main())
