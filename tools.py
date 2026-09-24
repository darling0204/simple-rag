def search_knowledge(
    query,
    model,
    index,
    chunks,
    top_k=3
):
    """
    搜索本地知识库。
    """

    from rag import retrieve

    results = retrieve(
        query,
        model,
        index,
        chunks,
        top_k
    )

    return [
        result["chunk"]
        for result in results
    ]


def calculator(expression):
    """
    计算简单的数学表达式。
    """

    try:
        result = eval(
            expression,
            {"__builtins__": {}},
            {}
        )

        return str(result)

    except Exception as e:
        return f"计算失败：{e}"