"""Agent 核心：工具定义、系统提示词、对话循环与流式输出。"""

import difflib
import json
import os
import time

from openai import OpenAI

from config import settings
from tools import (
    search_knowledge,
    search_knowledge_structured,
    _format_retrieval_results,
    calculator,
    read_file,
    search_code,
    write_file,
    run_test,
    edit_file,
)


# =========================
# 1. DeepSeek 客户端
# =========================

def create_client():
    """创建带超时与重试的 OpenAI 兼容客户端。"""
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError(
            "没有找到 DEEPSEEK_API_KEY，请检查 .env 或环境变量配置。"
        )

    return OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


# =========================
# 2. 工具定义
# =========================

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_knowledge",
        "description": (
            "搜索当前用户指定的本地知识库。"
            "当用户询问知识库中的概念、定义、公司制度或相关信息时使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "需要搜索的知识库问题",
                }
            },
            "required": ["query"],
        },
    },
}

CALCULATOR_TOOL = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": "计算数学表达式。当用户需要进行数学计算时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "需要计算的数学表达式，例如 123*456",
                }
            },
            "required": ["expression"],
        },
    },
}

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "读取项目中的文件内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要读取的项目文件路径，例如 api.py",
                }
            },
            "required": ["path"],
        },
    },
}

SEARCH_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_code",
        "description": "在项目代码文件中搜索关键词。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "要搜索的关键词",
                }
            },
            "required": ["keyword"],
        },
    },
}

WRITE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "创建新文件或整体重写项目中的文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要修改的项目文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "新的文件内容",
                },
            },
            "required": ["path", "content"],
        },
    },
}

RUN_TEST_TOOL = {
    "type": "function",
    "function": {
        "name": "run_test",
        "description": "运行项目中的 Python 测试文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "test_file": {
                    "type": "string",
                    "description": "要运行的测试文件路径",
                }
            },
            "required": ["test_file"],
        },
    },
}

EDIT_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": "对项目中的已有代码进行局部修改。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要修改的项目文件路径",
                },
                "old_text": {
                    "type": "string",
                    "description": "需要被替换的旧文本，必须唯一匹配",
                },
                "new_text": {
                    "type": "string",
                    "description": "新的文本内容",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
}

BASE_TOOLS = [SEARCH_TOOL, CALCULATOR_TOOL]
CODING_TOOLS = [
    READ_FILE_TOOL,
    SEARCH_CODE_TOOL,
    WRITE_FILE_TOOL,
    RUN_TEST_TOOL,
    EDIT_FILE_TOOL,
]


def get_available_tools():
    """根据配置返回当前可用的工具集。"""
    if settings.CODING_AGENT_ENABLED:
        return BASE_TOOLS + CODING_TOOLS
    return BASE_TOOLS


# =========================
# 3. System Prompt
# =========================

DEFAULT_SYSTEM_PROMPT = """
你是一个专业的企业 AI Agent，名为 Nova。

你可以使用以下工具：

1. search_knowledge：搜索当前用户指定的本地知识库。
2. calculator：计算数学表达式。

【知识库问答规则】

1. 当用户询问知识、概念、定义、说明、制度、流程等知识库相关内容时，
必须优先调用 search_knowledge。

2. search_knowledge 返回的内容是当前知识库提供的唯一事实来源。

3. 对于知识库问题，只能根据 search_knowledge 返回的内容回答。
不允许使用模型自身的通用知识补充、推测或编造答案。

4. 如果 search_knowledge 返回的内容中没有足够的信息，
必须明确告诉用户：“知识库中没有相关信息”。

5. 即使你知道某个问题的通用答案，只要这是知识库问答，
也不能使用知识库之外的信息。

6. 回答中应尽量说明信息来自哪个文档。

【计算规则】

如果用户需要数学计算，调用 calculator，并直接使用它返回的结果。

【通用规则】

- 回答简洁、准确、结构清晰，使用中文。
- 如果一个问题需要多个工具，分步骤调用；
  工具返回足够信息后，再生成最终回答。
- 回答完成后不要再继续调用工具。
"""

CODING_SYSTEM_PROMPT = """
你是一个 AI Coding Agent。

你的任务不是普通聊天，而是：
理解任务 → 搜索代码 → 阅读代码 → 分析问题 → 修改代码 →
运行测试 → 如果失败则自动修复 → 返回结果。

你可以使用以下工具：
search_code、read_file、edit_file、write_file、run_test、
search_knowledge、calculator。

【代码修改规则】
1. 修改前必须先用 read_file 阅读相关文件。
2. 修改时优先使用 edit_file，不要轻易用 write_file 重写整个文件。
3. old_text 必须唯一匹配，若不唯一请重新读取文件分析。
4. 不允许修改项目目录之外的文件。
5. 修改后必须运行测试。
6. 如果测试失败，分析错误，继续修复，最多自动修复 3 次。
7. 如果 3 次后仍失败，明确告诉用户失败原因和已尝试的修复。
8. 最终回答要说明：修改了哪些文件、修改原因、测试结果、是否修复成功。

【代码分析规则】
当用户要求分析项目结构、请求链路、接口实现时：
1. 使用 search_code 定位关键函数。
2. 使用 read_file 读取相关文件。
3. 根据真实代码回答，不要猜测。
"""


# =========================
# 4. 工具执行器
# =========================

def execute_tool(function_name, arguments, model, index, chunks, sources=None):
    if function_name == "search_knowledge":
        results = search_knowledge(
            arguments.get("query", ""),
            model,
            index,
            chunks,
            sources=sources,
        )
        return "\n\n".join(results)

    if function_name == "calculator":
        return calculator(arguments.get("expression", ""))

    if function_name == "read_file":
        return read_file(arguments.get("path", ""))

    if function_name == "search_code":
        return search_code(arguments.get("keyword", ""))

    if function_name == "write_file":
        return write_file(
            arguments.get("path", ""),
            arguments.get("content", ""),
        )

    if function_name == "run_test":
        return run_test(arguments.get("test_file", "agent_test.py"))

    if function_name == "edit_file":
        return edit_file(
            arguments.get("path", ""),
            arguments.get("old_text", ""),
            arguments.get("new_text", ""),
        )

    return f"未知工具：{function_name}"


# =========================
# 5. Diff 辅助
# =========================

def _read_project_file(path):
    project_root = os.path.abspath(os.path.dirname(__file__))
    target_path = os.path.abspath(os.path.join(project_root, path))

    try:
        if os.path.commonpath([project_root, target_path]) != project_root:
            return None, None
    except ValueError:
        return None, None

    if not os.path.isfile(target_path):
        return target_path, None

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return target_path, f.read()
    except Exception:
        return target_path, None


def _make_diff(path, old_content, new_content):
    old_content = old_content or ""
    new_content = new_content or ""

    diff = difflib.unified_diff(
        old_content.splitlines(),
        new_content.splitlines(),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(diff)


def _parse_tool_arguments(tool_call):
    try:
        return json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError:
        return {}


def _extract_sources(tool_call_log):
    """从工具调用日志中提取检索命中的来源文档。"""
    sources = set()
    for step in tool_call_log:
        if step.get("tool") != "search_knowledge":
            continue
        retrieved = step.get("retrieved")
        if isinstance(retrieved, list):
            for item in retrieved:
                if isinstance(item, dict) and item.get("source"):
                    sources.add(item["source"])
    return sorted(sources)


# =========================
# 6. Agent 对话循环
# =========================

class AgentError(RuntimeError):
    """Agent 执行失败。"""


def _build_messages(system_prompt, history, user_query):
    messages = [
        {
            "role": "system",
            "content": system_prompt or DEFAULT_SYSTEM_PROMPT,
        }
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_query})
    return messages


def agent(
    client,
    user_query,
    model,
    index,
    chunks,
    history=None,
    tool_call_log=None,
    max_rounds=5,
    system_prompt=None,
    sources=None,
):
    """非流式 Agent 对话。返回最终回答文本。"""
    messages = _build_messages(system_prompt, history, user_query)
    tools = get_available_tools()

    try:
        for round_number in range(max_rounds):
            response = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto" if tools else None,
            )

            message = response.choices[0].message

            if not message.tool_calls:
                return message.content or ""

            messages.append(message)

            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                arguments = _parse_tool_arguments(tool_call)

                step = {
                    "round": round_number + 1,
                    "tool": function_name,
                    "arguments": arguments,
                    "result": None,
                    "path": None,
                    "diff": None,
                }

                old_content = None
                target_path = None

                if function_name in ("write_file", "edit_file"):
                    target_path = arguments.get("path")
                    if target_path:
                        _, old_content = _read_project_file(target_path)
                        step["path"] = target_path

                if function_name == "search_knowledge":
                    retrieved = search_knowledge_structured(
                        arguments.get("query", ""),
                        model,
                        index,
                        chunks,
                        sources=sources,
                    )
                    step["retrieved"] = retrieved
                    raw_result = "\n\n".join(
                        _format_retrieval_results(retrieved)
                    )
                else:
                    raw_result = execute_tool(
                        function_name,
                        arguments,
                        model,
                        index,
                        chunks,
                        sources,
                    )

                step["result"] = raw_result

                if (
                    function_name in ("write_file", "edit_file")
                    and target_path
                ):
                    _, new_content = _read_project_file(target_path)
                    step["diff"] = _make_diff(
                        target_path, old_content, new_content
                    )

                if tool_call_log is not None:
                    tool_call_log.append(step)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": raw_result,
                    }
                )

        return "工具调用次数超过限制，暂时无法完成任务。"

    except AgentError:
        raise
    except Exception as exc:
        raise AgentError(f"模型调用失败：{exc}") from exc


def agent_stream(
    client,
    user_query,
    model,
    index,
    chunks,
    history=None,
    max_rounds=5,
    system_prompt=None,
    sources=None,
):
    """流式 Agent：先完成工具调用阶段，再流式输出最终回答。

    yield 事件字典：
      {"type": "tool_call", "round": int, "tool": str, "arguments": dict}
      {"type": "tool_result", "tool": str, "result": str}
      {"type": "delta", "content": str}
      {"type": "done", "answer": str, "sources": [...], "tool_calls": [...]}
      {"type": "error", "message": str}
    """
    messages = _build_messages(system_prompt, history, user_query)
    tools = get_available_tools()
    tool_call_log = []

    try:
        for round_number in range(max_rounds):
            response = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto" if tools else None,
            )

            message = response.choices[0].message

            if not message.tool_calls:
                break

            messages.append(message)

            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                arguments = _parse_tool_arguments(tool_call)

                yield {
                    "type": "tool_call",
                    "round": round_number + 1,
                    "tool": function_name,
                    "arguments": arguments,
                }

                if function_name == "search_knowledge":
                    retrieved = search_knowledge_structured(
                        arguments.get("query", ""),
                        model,
                        index,
                        chunks,
                        sources=sources,
                    )
                    raw_result = "\n\n".join(
                        _format_retrieval_results(retrieved)
                    )
                else:
                    raw_result = execute_tool(
                        function_name,
                        arguments,
                        model,
                        index,
                        chunks,
                        sources,
                    )

                yield {
                    "type": "tool_result",
                    "tool": function_name,
                    "result": raw_result[:2000],
                }

                tool_call_log.append(
                    {
                        "round": round_number + 1,
                        "tool": function_name,
                        "arguments": arguments,
                        "result": raw_result,
                        "retrieved": (
                            retrieved
                            if function_name == "search_knowledge"
                            else None
                        ),
                    }
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": raw_result,
                    }
                )
        else:
            yield {
                "type": "error",
                "message": "工具调用次数超过限制，暂时无法完成任务。",
            }
            return

        # 流式输出最终回答
        answer_parts = []
        stream = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                answer_parts.append(delta.content)
                yield {"type": "delta", "content": delta.content}

        answer = "".join(answer_parts)
        yield {
            "type": "done",
            "answer": answer,
            "sources": _extract_sources(tool_call_log),
            "tool_calls": tool_call_log,
        }

    except Exception as exc:
        yield {"type": "error", "message": f"模型调用失败：{exc}"}


# =========================
# 7. Coding Agent 入口
# =========================

def run_coding_agent(
    client,
    task,
    model,
    index,
    chunks,
    max_rounds=15,
):
    steps = []

    answer = agent(
        client=client,
        user_query=task,
        model=model,
        index=index,
        chunks=chunks,
        history=None,
        tool_call_log=steps,
        max_rounds=max_rounds,
        system_prompt=CODING_SYSTEM_PROMPT,
    )

    modified_files = []
    diffs = []

    for step in steps:
        if step.get("diff"):
            path = step.get("path")
            if path and path not in modified_files:
                modified_files.append(path)
            diffs.append({"path": path, "diff": step["diff"]})

    return {
        "answer": answer,
        "steps": steps,
        "modified_files": modified_files,
        "diffs": diffs,
    }


# =========================
# 8. 命令行入口
# =========================

def main():
    from rag import (
        load_documents,
        split_by_paragraph,
        get_embedding_model,
        create_embeddings,
        build_index,
    )

    print("========== AI Agent ==========")

    text = load_documents("data/knowledge.txt")
    chunks = split_by_paragraph(text)
    print(f"知识库 Chunk 数量：{len(chunks)}")

    model = get_embedding_model()
    embeddings = create_embeddings(model, chunks)
    index = build_index(embeddings)

    client = create_client()

    while True:
        query = input("\n请输入问题（输入 exit 退出）：")
        if query.lower() == "exit":
            break

        answer = agent(client, query, model, index, chunks)
        print("\n========== Agent 最终回答 ==========")
        print(answer)


if __name__ == "__main__":
    main()
