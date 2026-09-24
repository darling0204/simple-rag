import json
import os

from openai import OpenAI

from rag import (
    load_documents,
    split_by_paragraph,
    load_embedding_model,
    create_embeddings,
    build_index,
)

from tools import (
    search_knowledge,
    calculator,
)

from config import (
    LLM_MODEL,
    DEEPSEEK_BASE_URL,
)


# =========================
# 1. 创建 DeepSeek 客户端
# =========================

def create_client():

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise ValueError(
            "没有找到 DEEPSEEK_API_KEY"
        )

    return OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL
    )


# =========================
# 2. 定义 Agent 可以使用的工具
# =========================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "搜索本地知识库。当用户询问知识库中的概念、定义或相关信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "需要搜索的知识库问题"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式。当用户需要进行数学计算时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "需要计算的数学表达式，例如 123*456"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]


# =========================
# 3. Agent
# =========================

def agent(
    client,
    user_query,
    model,
    index,
    chunks,
    history=None,
    tool_call_log=None
):

    messages = [
        {
            "role": "system",
            "content": """
    你是一个 AI Agent。

    你可以使用以下工具：

    1. search_knowledge：
    搜索当前用户指定的本地知识库。

    2. calculator：
    计算数学表达式。

    请遵守以下规则：

    【知识库问答规则】
    1. 当用户询问知识、概念、定义、说明或知识库相关内容时，
    必须优先调用 search_knowledge。

    2. search_knowledge 返回的内容是当前知识库提供的唯一事实来源。

    3. 对于知识库问题，只能根据 search_knowledge 返回的内容回答。
    不允许使用模型自身的通用知识补充、推测或编造答案。

    4. 如果 search_knowledge 返回的内容中没有足够的信息，
    必须明确告诉用户：
    “知识库中没有相关信息”。

    5. 即使你知道某个问题的通用答案，
    只要这是知识库问答，也不能使用知识库之外的信息。

    【计算规则】
    如果用户需要数学计算，可以调用 calculator。
    计算结果应直接使用 calculator 返回的结果。

    【多工具规则】
    如果一个问题需要多个工具，
    可以按照任务需要分步骤调用工具。

    当工具已经返回足够的信息后，
    再生成最终回答。
    """
        }
    ]

    if history:
        messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": user_query
        }
    )

    # 最多允许连续调用 5 轮工具
    max_rounds = 5

    for round_number in range(max_rounds):

        print(
            f"\n========== Agent 第 {round_number + 1} 轮思考 =========="
        )

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )

        message = response.choices[0].message

        # 如果模型不再调用工具，返回最终答案
        if not message.tool_calls:

            return message.content

        # 保存 Assistant 的工具调用消息
        messages.append(message)

        # 执行本轮所有工具调用
        for tool_call in message.tool_calls:

            function_name = tool_call.function.name

            arguments = json.loads(
                tool_call.function.arguments
            )

            print("\n========== Agent 调用工具 ==========")
            print(f"工具：{function_name}")
            print(f"参数：{arguments}")
            if tool_call_log is not None:
                tool_call_log.append(function_name)
            if function_name == "search_knowledge":

                results = search_knowledge(
                    arguments["query"],
                    model,
                    index,
                    chunks
                )

                tool_result = "\n\n".join(results)

            elif function_name == "calculator":

                tool_result = calculator(
                    arguments["expression"]
                )

            else:

                tool_result = (
                    f"未知工具：{function_name}"
                )

            print("\n========== 工具返回结果 ==========")
            print(tool_result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                }
            )

    return "工具调用次数超过限制，暂时无法完成任务。"
# =========================
# 4. 主程序
# =========================

def main():

    print("========== AI Agent ==========")

    # 加载知识库
    text = load_documents(
        "data/knowledge.txt"
    )

    # 自然段切分
    chunks = split_by_paragraph(text)

    print(
        f"知识库 Chunk 数量：{len(chunks)}"
    )

    # 加载 Embedding 模型
    model = load_embedding_model()

    # 生成 Embedding
    embeddings = create_embeddings(
        model,
        chunks
    )

    # 建立 FAISS 索引
    index = build_index(
        embeddings
    )

    # 创建 DeepSeek 客户端
    client = create_client()

    # =========================
    # 开始对话
    # =========================

    while True:

        query = input(
            "\n请输入问题（输入 exit 退出）："
        )

        if query.lower() == "exit":
            break

        answer = agent(
            client,
            query,
            model,
            index,
            chunks
        )

        print(
            "\n========== Agent 最终回答 =========="
        )

        print(answer)


if __name__ == "__main__":
    main()