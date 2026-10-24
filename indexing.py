"""文档索引后台任务服务。

- 每个知识库一把锁，重建索引串行执行，避免并发写坏文件；
- 上传/删除文档后异步重建，接口快速返回；
- 文档状态写入数据库，前端可轮询。
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from database import Document, SessionLocal
from rag import (
    remove_knowledge_base_index,
    save_knowledge_base_index,
)


logger = logging.getLogger("nova.indexing")

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="indexer")


def _kb_lock(knowledge_base_id: int) -> threading.Lock:
    with _locks_guard:
        if knowledge_base_id not in _locks:
            _locks[knowledge_base_id] = threading.Lock()
        return _locks[knowledge_base_id]


def _rebuild(knowledge_base_id: int):
    """在一个独立数据库会话中重建索引。"""
    db = SessionLocal()
    try:
        documents = db.query(Document).filter(
            Document.knowledge_base_id == knowledge_base_id
        ).all()

        for doc in documents:
            doc.status = "indexing"
            doc.error_message = ""
        db.commit()

        file_paths = [doc.file_path for doc in documents]
        display_names = [doc.filename for doc in documents]

        if not file_paths:
            remove_knowledge_base_index(knowledge_base_id)
            return

        stats = save_knowledge_base_index(
            knowledge_base_id, file_paths, display_names
        )

        for doc in documents:
            doc.status = "ready"
            doc.chunk_count = stats["chunk_count"] // max(
                len(file_paths), 1
            )
        db.commit()
        logger.info(
            "知识库 %s 索引重建完成：%s 个文档，%s 个文本块",
            knowledge_base_id,
            stats["document_count"],
            stats["chunk_count"],
        )

    except Exception as exc:
        logger.exception("知识库 %s 索引重建失败", knowledge_base_id)
        db.rollback()
        try:
            documents = db.query(Document).filter(
                Document.knowledge_base_id == knowledge_base_id
            ).all()
            for doc in documents:
                doc.status = "failed"
                doc.error_message = str(exc)[:500]
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def schedule_rebuild(knowledge_base_id: int):
    """异步调度索引重建（不等待完成）。"""

    def _run_with_lock():
        with _kb_lock(knowledge_base_id):
            _rebuild(knowledge_base_id)

    _executor.submit(_run_with_lock)


def is_rebuilding(knowledge_base_id: int) -> bool:
    lock = _kb_lock(knowledge_base_id)
    return lock.locked()


def shutdown():
    _executor.shutdown(wait=True, cancel_futures=True)
