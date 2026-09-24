import os
import json
import faiss
from openai import OpenAI
from sentence_transformers import SentenceTransformer

from config import (
    TOP_K,
    EMBEDDING_MODEL,
    LLM_MODEL,
    DEEPSEEK_BASE_URL,
)


def load_documents(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


# 按自然段切分文本
def split_by_paragraph(text):
    paragraphs = text.split("\n\n")

    chunks = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if paragraph:
            chunks.append(paragraph)

    return chunks

def load_uploaded_document(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    return split_by_paragraph(text)

def load_embedding_model():
    print("正在加载 Embedding 模型...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    return model


def create_embeddings(model, chunks):
    print("正在生成 Embedding...")
    embeddings = model.encode(chunks)

    return embeddings


def build_index(embeddings):
    dimension = embeddings.shape[1]

    index = faiss.IndexFlatL2(dimension)

    index.add(embeddings)

    return index

def build_knowledge_base_index(file_path):
    # 1. 读取上传文件
    chunks = load_uploaded_document(file_path)

    # 2. 加载 Embedding 模型
    model = load_embedding_model()

    # 3. 生成向量
    embeddings = create_embeddings(model, chunks)

    # 4. 建立 FAISS 索引
    index = build_index(embeddings)

    return model, index, chunks

#按知识库保存完整FAISS索引

def save_knowledge_base_index(
    knowledge_base_id,
    file_paths
):
    import os
    import json
    import faiss

    model, index, chunks = build_knowledge_base_from_documents(
        file_paths
    )

    os.makedirs("indexes", exist_ok=True)

    index_path = f"indexes/kb_{knowledge_base_id}.index"
    chunks_path = f"indexes/kb_{knowledge_base_id}_chunks.json"

    faiss.write_index(
        index,
        index_path
    )

    with open(
        chunks_path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            chunks,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"知识库 {knowledge_base_id} 索引保存成功"
    )
    #加载知识库索引
def load_knowledge_base_index(knowledge_base_id):
    import os
    import json

    index_path = os.path.join(
        "indexes",
        f"kb_{knowledge_base_id}.index"
    )

    chunks_path = os.path.join(
        "indexes",
        f"kb_{knowledge_base_id}_chunks.json"
    )

    if not os.path.exists(index_path):
        raise FileNotFoundError(
            f"知识库 {knowledge_base_id} 的 FAISS 索引不存在"
        )

    if not os.path.exists(chunks_path):
        raise FileNotFoundError(
            f"知识库 {knowledge_base_id} 的文本块不存在"
        )

    # 加载 FAISS
    index = faiss.read_index(index_path)

    # 加载文本块
    with open(
        chunks_path,
        "r",
        encoding="utf-8"
    ) as f:
        chunks = json.load(f)

    # 加载 Embedding 模型
    model = load_embedding_model()

    return model, index, chunks



    # 保存 FAISS 索引
    index_path = os.path.join(
        "indexes",
        f"kb_{knowledge_base_id}.index"
    )

    faiss.write_index(
        index,
        index_path
    )

    # 保存文本块
    chunks_path = os.path.join(
        "indexes",
        f"kb_{knowledge_base_id}_chunks.json"
    )

    with open(
        chunks_path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            chunks,
            f,
            ensure_ascii=False,
            indent=2
        )

    return {
        "index_path": index_path,
        "chunks_path": chunks_path,
        "chunks": chunks
    }



    import os

    model, index, chunks = build_knowledge_base_from_documents(
        file_paths
    )

    os.makedirs("indexes", exist_ok=True)

    index_path = os.path.join(
        "indexes",
        f"kb_{knowledge_base_id}.index"
    )

    faiss.write_index(
        index,
        index_path
    )

    return {
        "index_path": index_path,
        "chunks": chunks
    }



    os.makedirs("indexes", exist_ok=True)

    index_path = os.path.join(
        "indexes",
        f"kb_{knowledge_base_id}.index"
    )

    faiss.write_index(
        index,
        index_path
    )

    return {
        "index_path": index_path,
        "chunks": chunks
    }

#读取知识库全部文档
def build_knowledge_base_from_documents(file_paths):
    all_chunks = []

    for file_path in file_paths:
        chunks = load_uploaded_document(file_path)
        all_chunks.extend(chunks)

    model = load_embedding_model()

    embeddings = create_embeddings(
        model,
        all_chunks
    )

    index = build_index(embeddings)

    return model, index, all_chunks





def retrieve(query, model, index, chunks, top_k=TOP_K):
    query_embedding = model.encode([query])

    distances, indices = index.search(
        query_embedding,
        top_k
    )

    results = []

    for distance, index_id in zip(
        distances[0],
        indices[0]
    ):
        results.append({
            "chunk_id": int(index_id),
            "distance": float(distance),
            "chunk": chunks[index_id]
        })

    return results


def generate(query, results):

    context = "\n\n".join(
        result["chunk"]
        for result in results
    )

    prompt = f"""
你是一个知识库问答助手。

请严格根据下面提供的知识库内容回答用户的问题。

要求：
1. 只能使用知识库中的信息。
2. 如果知识库中没有答案，请回答“知识库中没有相关信息”。
3. 不要编造知识库中不存在的信息。
4. 回答简洁、准确。

【知识库内容】
{context}

【用户问题】
{query}
"""

    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise ValueError(
            "没有找到 DEEPSEEK_API_KEY，请先设置 API Key。"
        )

    client = OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是一个严格基于知识库回答问题的助手。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content


def main():

    file_path = "data/knowledge.txt"

    # 1. 加载知识库
    text = load_documents(file_path)

    # 2. 按自然段切分
    chunks = split_by_paragraph(text)

    print("\n========== 文本切分结果 ==========")
    print(f"知识库共切分为 {len(chunks)} 个文本块")

    for i, chunk in enumerate(chunks):
        print(f"\n--- Chunk {i} ---")
        print(chunk)

    # 3. 加载 Embedding 模型
    model = load_embedding_model()

    # 4. 生成向量
    embeddings = create_embeddings(model, chunks)

    # 5. 建立 FAISS 索引
    index = build_index(embeddings)

    # 6. 用户提问
    while True:

        query = input("\n请输入问题：")

        if query.lower() == "exit":
            break

        # 7. 检索
        results = retrieve(
            query,
            model,
            index,
            chunks
        )

        print("\n========== 检索结果 ==========")

        for i, result in enumerate(results, start=1):
            print(f"\n--- Top {i} ---")
            print(f"Chunk编号：{result['chunk_id']}")
            print(f"距离：{result['distance']:.4f}")
            print(f"内容：{result['chunk']}")

        # 8. 生成答案
        answer = generate(query, results)

        print("\n========== 最终答案 ==========")
        print(answer)


if __name__ == "__main__":
    main()