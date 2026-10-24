from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Simple RAG Agent MCP")


@mcp.tool()
def get_project_info() -> str:
    """获取 Simple RAG Agent 项目的基本信息。"""
    return """
项目名称：Simple RAG Agent
项目类型：AI 知识库问答与 Agent 应用平台
技术栈：FastAPI + React + FAISS + DeepSeek
核心能力：RAG、Tool Calling、Agent、Coding Agent
"""
@mcp.tool()
def list_project_files() -> str:
    """列出项目中的主要文件和目录。"""
    import os

    project_root = os.path.dirname(os.path.abspath(__file__))

    results = []

    for root, dirs, files in os.walk(project_root):
        # 忽略不需要展示的目录
        dirs[:] = [
            d for d in dirs
            if d not in {".git", ".venv", "node_modules", "__pycache__", "dist"}
        ]

        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, project_root)
            results.append(relative_path)

    return "\n".join(sorted(results))

if __name__ == "__main__":
    mcp.run()