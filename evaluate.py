
from rag import (
    load_documents,
    split_by_paragraph,
    load_embedding_model,
    create_embeddings,
    build_index,
    retrieve,
)

from agent import agent, create_client
from config import TOP_K


# =========================
# 1. 测试问题
# =========================

TEST_CASES = [
    {
        "question": "什么是RAG？",
        "expected_chunks": [2, 3],
        "keywords": ["检索增强生成", "知识库", "大语言模型"],
    },
    {
        "question": "什么是Embedding？",
        "expected_chunks": [4],
        "keywords": ["文本", "向量", "语义"],
    },
    {
        "question": "什么是向量数据库？",
        "expected_chunks": [5],
        "keywords": ["向量", "存储", "检索"],
    },
    {
        "question": "什么是Top-K？",
        "expected_chunks": [6],
        "keywords": ["最相关", "文本片段", "K"],
    },
    {
        "question": "什么是Agent？",
        "expected_chunks": [7],
        "keywords": ["任务目标", "规划", "工具"],
    },
    {
        "question": "什么是Function Calling？",
        "expected_chunks": [8],
        "keywords": ["大语言模型", "调用", "工具"],
    },
    {
        "question": "RAG和Agent有什么关系？",
        "expected_chunks": [9],
        "keywords": ["知识库", "工具", "Agent"],
    },
]

TOOL_TEST_CASES = [
    {
        "question": "什么是RAG？",
        "expected_tools": ["search_knowledge"],
    },
    {
        "question": "123 * 456 等于多少？",
        "expected_tools": ["calculator"],
    },
    {
        "question": "根据知识库，Top-K设置为3表示检索多少个文本片段？如果进行2次这样的检索，一共是多少个文本片段？",
        "expected_tools": [
            "search_knowledge",
            "calculator",
        ],
    },
]

# =========================
# 2. 检索命中率评测
# =========================

def evaluate_retrieval(
    question,
    expected_chunks,
    model,
    index,
    chunks
):
    results = retrieve(
        question,
        model,
        index,
        chunks,
        TOP_K
    )

    retrieved_chunks = [
        result["chunk_id"]
        for result in results
    ]

    hit = any(
        chunk_id in retrieved_chunks
        for chunk_id in expected_chunks
    )

    return hit, retrieved_chunks, results


# =========================
# 3. 答案正确率评测
# =========================

def evaluate_answer(
    answer,
    keywords
):
    """
    判断最终答案是否包含所有关键知识点。
    """

    matched_keywords = [
        keyword
        for keyword in keywords
        if keyword.lower() in answer.lower()
    ]

    missing_keywords = [
        keyword
        for keyword in keywords
        if keyword.lower() not in answer.lower()
    ]

    correct = len(missing_keywords) == 0

    return correct, matched_keywords, missing_keywords


# =========================
# 4. 主评测程序
# =========================

def main():

    print("========== RAG 答案正确率自动评测 ==========")

    # =========================
    # 加载知识库
    # =========================

    text = load_documents(
        "data/knowledge.txt"
    )

    chunks = split_by_paragraph(
        text
    )

    print(
        f"\n知识库 Chunk 数量：{len(chunks)}"
    )

    print(
        f"当前 TOP_K：{TOP_K}"
    )

    # =========================
    # 加载 Embedding 模型
    # =========================

    model = load_embedding_model()

    embeddings = create_embeddings(
        model,
        chunks
    )

    index = build_index(
        embeddings
    )

    # =========================
    # 创建 LLM Client
    # =========================

    client = create_client()

    # =========================
    # 统计数据
    # =========================

    total = len(TEST_CASES)

    retrieval_hit_count = 0
    answer_correct_count = 0
    tool_success_count = 0

    # =========================
    # 开始评测
    # =========================

    for i, test_case in enumerate(
        TEST_CASES,
        start=1
    ):

        question = test_case["question"]

        expected_chunks = test_case[
            "expected_chunks"
        ]

        keywords = test_case[
            "keywords"
        ]

        print("\n")
        print("=" * 50)
        print(f"测试 {i}")
        print(f"问题：{question}")

        # =========================
        # ① 检索评测
        # =========================

        hit, retrieved_chunks, results = evaluate_retrieval(
            question,
            expected_chunks,
            model,
            index,
            chunks
        )

        if hit:
            retrieval_hit_count += 1
            retrieval_status = "✓ 命中"
        else:
            retrieval_status = "✗ 未命中"

        print(
            f"期望 Chunk：{expected_chunks}"
        )

        print(
            f"实际 Top-{TOP_K}：{retrieved_chunks}"
        )

        print(
            f"检索结果：{retrieval_status}"
        )

        # =========================
        # ② Agent 生成答案
        # =========================

        print("\n========== Agent 生成答案 ==========")

        tool_call_log = []

        answer = agent(
            client,
            question,
            model,
            index,
            chunks,
            history=None,
            tool_call_log=tool_call_log
        )

        print(
            f"\n最终答案：{answer}"
        )

        # =========================
        # ③ 答案正确性评测
        # =========================

        correct, matched, missing = evaluate_answer(
            answer,
            keywords
        )

        if correct:
            answer_correct_count += 1
            answer_status = "✓ 正确"
        else:
            answer_status = "✗ 可能存在问题"

        print(
            f"\n要求包含的关键知识点：{keywords}"
        )

        print(
            f"已命中关键词：{matched}"
        )

        print(
            f"缺失关键词：{missing}"
        )

        print(
            f"答案评测：{answer_status}"
        )

    print("\n")
    print("=" * 50)
    print("========== Tool Calling 评测 ==========")

    tool_total = len(TOOL_TEST_CASES)

    for i, test_case in enumerate(
        TOOL_TEST_CASES,
        start=1
    ):

        question = test_case["question"]

        expected_tools = test_case["expected_tools"]

        tool_call_log = []

        print(f"\n[{i}] {question}")

        answer = agent(
            client,
            question,
            model,
            index,
            chunks,
            history=None,
            tool_call_log=tool_call_log
        )

        print(
            f"期望工具：{expected_tools}"
        )

        print(
            f"实际调用：{tool_call_log}"
        )

        # 判断期望工具是否全部被调用
        success = all(
            tool in tool_call_log
            for tool in expected_tools
        )

        if success:
            tool_success_count += 1
            print("结果：✓ Tool Calling 成功")
        else:
            print("结果：✗ Tool Calling 失败")

    # =========================
    # 4. 最终统计
    # =========================

    retrieval_hit_rate = (
        retrieval_hit_count / total
    )

    answer_correct_rate = (
        answer_correct_count / total
    )

    print("\n")
    print("=" * 50)
    print("========== 评测总结 ==========")

    print(
        f"测试问题数：{total}"
    )

    print(
        f"检索命中数量：{retrieval_hit_count}"
    )

    print(
        f"检索命中率：{retrieval_hit_rate:.2%}"
    )

    print(
        f"答案正确数量：{answer_correct_count}"
    )

    print(
        f"答案正确率：{answer_correct_rate:.2%}"
    )

    tool_success_rate = (
        tool_success_count / tool_total
    )

    print(
        f"Tool Calling 成功数量：{tool_success_count}"
    )

    print(
        f"Tool Calling 成功率：{tool_success_rate:.2%}"
    )

if __name__ == "__main__":
    main()

