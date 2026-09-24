import json
import os

from openai import OpenAI

from agent import agent, create_client
from rag import (
    load_embedding_model,
)
from config import DEEPSEEK_BASE_URL


# =========================
# Eval 配置
# =========================

KNOWLEDGE_BASE_ID = 2

EVAL_FILE = "tests/eval_cases.json"

INDEX_FILE = f"indexes/kb_{KNOWLEDGE_BASE_ID}.index"
CHUNKS_FILE = f"indexes/kb_{KNOWLEDGE_BASE_ID}_chunks.json"


# =========================
# 加载 Eval 数据
# =========================

def load_eval_cases():

    with open(
        EVAL_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# =========================
# 加载知识库索引
# =========================

def load_knowledge_base():

    if not os.path.exists(INDEX_FILE):
        raise FileNotFoundError(
            f"找不到知识库索引：{INDEX_FILE}"
        )

    if not os.path.exists(CHUNKS_FILE):
        raise FileNotFoundError(
            f"找不到知识库文本：{CHUNKS_FILE}"
        )

    # 这里直接使用你项目现有的加载函数
    from rag import load_knowledge_base_index

    model, index, chunks = load_knowledge_base_index(
        KNOWLEDGE_BASE_ID
    )

    return model, index, chunks


# =========================
# 判断 Eval 是否通过
# =========================

def check_result(answer, expected_keywords):

    if not answer:
        return False

    answer_lower = answer.lower()

    for keyword in expected_keywords:

        if keyword.lower() not in answer_lower:
            return False

    return True


# =========================
# 主程序
# =========================

def main():

    print("\n========== AI Agent Evals ==========\n")

    # 1. 加载测试数据
    eval_cases = load_eval_cases()

    print(
        f"测试用例数量：{len(eval_cases)}"
    )

    # 2. 加载知识库
    print("\n正在加载知识库...")

    model, index, chunks = load_knowledge_base()

    print(
        f"知识库加载成功，Chunk 数量：{len(chunks)}"
    )

    # 3. 创建 DeepSeek Client
    client = create_client()

    # 4. 开始测试
    passed = 0
    failed = 0

    for case in eval_cases:

        print("\n" + "=" * 60)

        print(
            f"测试 {case['id']} "
            f"[{case['type']}]"
        )

        print(
            f"问题：{case['question']}"
        )

        # 记录 Agent 调用了什么工具
        tool_call_log = []

        try:

            answer = agent(
                client,
                case["question"],
                model,
                index,
                chunks,
                tool_call_log=tool_call_log
            )

            print(
                f"\nAgent回答：\n{answer}"
            )

            print(
                f"\n工具调用：{tool_call_log}"
            )

            # 判断答案
            result = check_result(
                answer,
                case["expected_keywords"]
            )

            if result:

                print("\n结果：PASS")
                passed += 1

            else:

                print("\n结果：FAIL")
                failed += 1

        except Exception as e:

            print(
                f"\n测试发生异常：{e}"
            )

            print("\n结果：FAIL")

            failed += 1

    # =========================
    # 最终结果
    # =========================

    total = len(eval_cases)

    if total > 0:
        pass_rate = passed / total * 100
    else:
        pass_rate = 0

    print("\n")
    print("=" * 60)
    print("========== Eval 最终结果 ==========")
    print("=" * 60)

    print(
        f"总测试数：{total}"
    )

    print(
        f"通过：{passed}"
    )

    print(
        f"失败：{failed}"
    )

    print(
        f"通过率：{pass_rate:.1f}%"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()