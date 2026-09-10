import logging
import os
from mcp.server.mcpserver import MCPServer
from mcp_server.registry import ToolRegistry
import mcp_server.tools as tools_pkg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omega-mcp-server")


def create_server() -> MCPServer:
    server = MCPServer(name="omega-mcp-server")

    # 1. Instantiate registry
    registry = ToolRegistry()

    # 2. Discover all BaseTool implementations in tools/
    registry.autodiscover(tools_pkg)

    # 3. Bind to MCP server
    registry.bind_to_mcp(server)

    return server


mcp = create_server()

if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8080"))

    mcp.run(transport="sse", host=host, port=port)