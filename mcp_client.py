import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


server_params = StdioServerParameters(
    command=sys.executable or "python",
    args=["mcp_server.py"],
)


async def main():
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            # 初始化 MCP 连接
            await session.initialize()

            # 获取 Server 提供的工具
            tools = await session.list_tools()

            print("发现的 MCP Tools：")

            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")

            # 调用 get_project_info
            result = await session.call_tool(
                "get_project_info",
                {}
            )

            print("\n调用结果：")
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
