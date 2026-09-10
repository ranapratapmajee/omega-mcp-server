import asyncio
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


async def main():
    async with sse_client("http://localhost:8080/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List registered tools
            tools = await session.list_tools()
            print("Available Tools:", [t.name for t in tools.tools])

            # 2. Call get_system_status
            result = await session.call_tool(
                "get_system_status", arguments={"include_memory": True}
            )
            print("\nTool Output:", result.content[0].text)


asyncio.run(main())