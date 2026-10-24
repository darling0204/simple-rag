"""RAG 核心：文档切分、Embedding、FAISS 索引与检索。

设计要点：
- Embedding 模型全局单例，避免每次请求重复加载；
- 索引文件原子写入（临时文件 + rename），避免并发读写损坏；
- 文本块附带来源文件名，回答时可引用来源；
- 兼容旧版 chunks JSON（纯列表）与新版（字典带 sources）。
"""

import json
import os
import re
import threading

import faiss
from sentence_transformers import SentenceTransformer

from config import (
    EMBEDDING_MODEL,
    settings,
)


INDEXES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexes")

_MODEL_LOCK = threading.Lock()
_EMBEDDING_MODEL = None
_MODEL_NAME_LOADED = None

_DEFAULT_KB_LOCK = threading.Lock()
_DEFAULT_KB_CACHE = None


# =========================
# 文本切分
# =========================

def load_documents(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def split_by_paragraph(text):
    """按空行切分段落，适合结构清晰的文本。"""
    chunks = []
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            chunks.append(paragraph)
    return chunks


def _split_long_paragraph(paragraph, chunk_size, overlap):
    """把过长段落进一步按句子和固定长度切块。"""
    sentences = re.split(r"(?<=[。！？.!?])\s*", paragraph)

    pieces = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= chunk_size:
            pieces.append(sentence)
            continue
        # 超长句子按窗口切分
        start = 0
        while start < len(sentence):
            pieces.append(sentence[start:start + chunk_size])
            start += chunk_size - overlap

    chunks = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + len(piece) + 1 <= chunk_size:
            current += " " + piece
        else:
            chunks.append(current)
            current = piece

    if current:
        chunks.append(current)

    return chunks


def chunk_text(text, chunk_size=None, overlap=None):
    """按大小+重叠切分文本，返回非空文本块列表。"""
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP

    if chunk_size <= 0:
        chunk_size = settings.CHUNK_SIZE
    if overlap >= chunk_size:
        overlap = chunk_size // 4

    paragraphs = split_by_paragraph(text)

    chunks = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            chunks.append(paragraph)
        else:
            chunks.extend(
                _split_long_paragraph(paragraph, chunk_size, overlap)
            )

    return chunks


def load_document_chunks(file_path):
    """读取上传文档并切块，返回 (文本块列表, 来源文件名)。"""
    text = load_documents(file_path)
    return chunk_text(text), os.path.basename(file_path)


# =========================
# Embedding 模型（全局单例）
# =========================

def get_embedding_model():
    """获取全局共享的 Embedding 模型，线程安全。"""
    global _EMBEDDING_MODEL, _MODEL_NAME_LOADED

    with _MODEL_LOCK:
        if _EMBEDDING_MODEL is None or _MODEL_NAME_LOADED != EMBEDDING_MODEL:
            _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL)
            _MODEL_NAME_LOADED = EMBEDDING_MODEL
        return _EMBEDDING_MODEL


def embedding_model_loaded() -> bool:
    return _EMBEDDING_MODEL is not None


def load_embedding_model():
    """兼容旧调用方的别名。"""
    return get_embedding_model()


def create_embeddings(model, chunks):
    if not chunks:
        dimension = model.get_sentence_embedding_dimension()
        import numpy as np

        return np.zeros((0, dimension), dtype="float32")
    return model.encode(chunks)


def build_index(embeddings):
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    if len(embeddings) > 0:
        index.add(embeddings)
    return index


# =========================
# 知识库索引构建与读写
# =========================

def build_knowledge_base_from_documents(
    file_paths, display_names=None
):
    """读取多个文档构建索引，返回 (model, index, chunks, sources)。"""
    all_chunks = []
    all_sources = []

    display_names = display_names or []
    for position, file_path in enumerate(file_paths):
        chunks, source = load_document_chunks(file_path)
        if position < len(display_names) and display_names[position]:
            source = display_names[position]
        all_chunks.extend(chunks)
        all_sources.extend([source] * len(chunks))

    model = get_embedding_model()
    embeddings = create_embeddings(model, all_chunks)
    index = build_index(embeddings)

    return model, index, all_chunks, all_sources


def _index_paths(knowledge_base_id):
    index_path = os.path.join(
        INDEXES_DIR, f"kb_{knowledge_base_id}.index"
    )
    chunks_path = os.path.join(
        INDEXES_DIR, f"kb_{knowledge_base_id}_chunks.json"
    )
    return index_path, chunks_path


def _atomic_write_json(path, payload):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def save_knowledge_base_index(
    knowledge_base_id, file_paths, display_names=None
):
    """重建并保存知识库索引（原子写入），返回统计信息。"""
    os.makedirs(INDEXES_DIR, exist_ok=True)

    _, index, chunks, sources = build_knowledge_base_from_documents(
        file_paths, display_names
    )

    index_path, chunks_path = _index_paths(knowledge_base_id)

    index_temp = f"{index_path}.tmp"
    faiss.write_index(index, index_temp)

    _atomic_write_json(
        chunks_path,
        {
            "chunks": chunks,
            "sources": sources,
        },
    )
    os.replace(index_temp, index_path)

    return {
        "chunk_count": len(chunks),
        "document_count": len(file_paths),
    }


def remove_knowledge_base_index(knowledge_base_id):
    """删除知识库的索引文件（幂等）。"""
    index_path, chunks_path = _index_paths(knowledge_base_id)
    for path in (index_path, chunks_path):
        if os.path.exists(path):
            os.remove(path)


def load_knowledge_base_index(knowledge_base_id):
    """加载知识库索引，返回 (model, index, chunks, sources)。"""
    index_path, chunks_path = _index_paths(knowledge_base_id)

    if not os.path.exists(index_path) or not os.path.exists(chunks_path):
        raise FileNotFoundError(
            f"知识库 {knowledge_base_id} 的索引尚未建立"
        )

    index = faiss.read_index(index_path)

    with open(chunks_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        # 兼容旧格式：纯文本块列表，无来源信息
        chunks = payload
        sources = [""] * len(chunks)
    else:
        chunks = payload.get("chunks", [])
        sources = payload.get("sources", [""] * len(chunks))

    model = get_embedding_model()

    return model, index, chunks, sources


def knowledge_base_index_exists(knowledge_base_id):
    index_path, chunks_path = _index_paths(knowledge_base_id)
    return os.path.exists(index_path) and os.path.exists(chunks_path)


def get_default_knowledge():
    """Coding Agent 使用的默认知识库（懒加载，全局缓存）。"""
    global _DEFAULT_KB_CACHE

    with _DEFAULT_KB_LOCK:
        if _DEFAULT_KB_CACHE is None:
            knowledge_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data",
                "knowledge.txt",
            )
            model, index, chunks, sources = (
                build_knowledge_base_from_documents([knowledge_file])
            )
            _DEFAULT_KB_CACHE = (model, index, chunks, sources)
        return _DEFAULT_KB_CACHE


# =========================
# 检索与生成
# =========================

def retrieve(query, model, index, chunks, top_k=None, sources=None):
    """检索最相关文本块，返回带来源的结果列表。"""
    top_k = top_k or settings.TOP_K
    sources = sources or [""] * len(chunks)

    if index.ntotal == 0 or not chunks:
        return []

    query_embedding = model.encode([query])
    top_k = min(top_k, index.ntotal)

    distances, indices = index.search(query_embedding, top_k)

    results = []
    for distance, index_id in zip(distances[0], indices[0]):
        if int(index_id) < 0 or int(index_id) >= len(chunks):
            continue
        results.append(
            {
                "chunk_id": int(index_id),
                "distance": float(distance),
                "chunk": chunks[index_id],
                "source": sources[index_id] if index_id < len(sources) else "",
            }
        )

    return results
