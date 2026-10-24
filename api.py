"""Nova Agent API：RAG + Agent + 用户体系的企业级后端。"""

import atexit
import json
import logging
import os
import time
import uuid
import atexit
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from agent import (
    AgentError,
    agent,
    agent_stream,
    create_client,
    run_coding_agent,
)
from config import settings
from database import (
    AuditLog,
    Conversation,
    Document,
    KnowledgeBase,
    Message,
    SessionLocal,
    User,
    get_db,
    run_migrations,
    utcnow,
)
from indexing import is_rebuilding, schedule_rebuild
from logging_config import setup_logging
from middleware import RequestContextMiddleware, unhandled_exception_handler
from rag import (
    get_default_knowledge,
    remove_knowledge_base_index,
    knowledge_base_index_exists,
    load_knowledge_base_index,
)
from schemas import (
    ChatRequest,
    CodingAgentRequest,
    ConversationCreate,
    KnowledgeBaseCreate,
    LoginRequest,
    RefreshTokenRequest,
    UserCreate,
)
from security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_admin,
    get_current_user,
    hash_password,
    rate_limit,
    verify_password,
)


# =========================
# 初始化
# =========================

setup_logging()
logger = logging.getLogger("nova.api")

run_migrations()

app = FastAPI(
    title=settings.APP_NAME,
    description="企业级 RAG + Agent 智能问答平台",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(Exception, unhandled_exception_handler)

_client = None


def get_client():
    """DeepSeek 客户端懒加载单例。"""
    global _client
    if _client is None:
        _client = create_client()
    return _client


def write_audit(
    db: Session,
    user_id,
    action: str,
    detail: str = "",
    request: Request = None,
):
    ip = ""
    if request is not None and request.client is not None:
        ip = request.client.host or ""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            detail=detail[:500],
            ip_address=ip,
        )
    )
    db.commit()


def _kb_dict(kb: KnowledgeBase):
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description or "",
        "user_id": kb.user_id,
        "created_at": kb.created_at,
        "updated_at": kb.updated_at,
    }


def _conversation_dict(conversation: Conversation):
    return {
        "id": conversation.id,
        "title": conversation.title,
        "user_id": conversation.user_id,
        "knowledge_base_id": conversation.knowledge_base_id,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def _message_dict(message: Message):
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "sources": json.loads(message.sources or "[]"),
        "created_at": message.created_at,
    }


def _document_dict(document: Document):
    return {
        "id": document.id,
        "filename": document.filename,
        "size": document.size,
        "chunk_count": document.chunk_count,
        "status": document.status,
        "error_message": document.error_message,
        "created_at": document.created_at,
    }


def get_user_knowledge_base(
    knowledge_base_id: int, user: User, db: Session
) -> KnowledgeBase:
    """获取属于当前用户的知识库，不存在则 404。"""
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.user_id == user.id,
    ).first()
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return knowledge_base


def _load_kb_or_503(knowledge_base_id: int):
    """加载知识库索引；未就绪时返回 503。"""
    try:
        return load_knowledge_base_index(knowledge_base_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="知识库索引尚未就绪，请稍候或先上传文档",
        ) from exc


# =========================
# 健康检查
# =========================

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.query(User.id).limit(1).all()
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "components": {
            "database": "ok" if db_ok else "error",
            "llm": (
                "configured" if settings.DEEPSEEK_API_KEY else "missing_key"
            ),
            "embedding_model": (
                "loaded" if _embedding_loaded() else "lazy",
            ),
        },
        "time": datetime.now(timezone.utc).isoformat(),
    }


def _embedding_loaded() -> bool:
    from rag import embedding_model_loaded

    return embedding_model_loaded()


# =========================
# 用户认证
# =========================

@app.post("/register", dependencies=[Depends(rate_limit)])
def register(
    request: UserCreate,
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(
        User.username == request.username
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = User(
        username=request.username,
        password=hash_password(request.password),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="注册失败，请稍后重试")

    write_audit(db, user.id, "register")
    return {
        "id": user.id,
        "username": user.username,
        "message": "注册成功",
    }


@app.post("/login", dependencies=[Depends(rate_limit)])
def login(
    request: LoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.username == request.username.strip()
    ).first()

    if not user or not verify_password(request.password, user.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token, access_expire = create_access_token(user)
    refresh_token, _ = create_refresh_token(user)

    write_audit(db, user.id, "login", request=http_request)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin,
        },
    }


@app.post("/refresh", dependencies=[Depends(rate_limit)])
def refresh_access_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    payload = decode_token(request.refresh_token, "refresh")

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Refresh Token 无效")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    access_token, access_expire = create_access_token(user)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@app.get("/users/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at,
    }


# =========================
# 知识库管理
# =========================

@app.post(
    "/knowledge-bases",
    dependencies=[Depends(rate_limit)],
)
def create_knowledge_base(
    request: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge_base = KnowledgeBase(
        name=request.name,
        description=request.description,
        user_id=current_user.id,
    )
    db.add(knowledge_base)
    db.commit()
    db.refresh(knowledge_base)
    return _kb_dict(knowledge_base)


@app.get("/knowledge-bases")
def get_knowledge_bases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge_bases = db.query(KnowledgeBase).filter(
        KnowledgeBase.user_id == current_user.id
    ).order_by(KnowledgeBase.id.desc()).all()
    return [_kb_dict(kb) for kb in knowledge_bases]


@app.delete("/knowledge-bases/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: int,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    knowledge_base = get_user_knowledge_base(
        knowledge_base_id, current_user, db
    )

    documents = db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base_id
    ).all()
    for document in documents:
        if document.file_path and os.path.exists(document.file_path):
            try:
                os.remove(document.file_path)
            except OSError:
                logger.warning("删除文档文件失败：%s", document.file_path)

    # ORM 级联删除文档、会话与消息
    db.delete(knowledge_base)
    db.commit()

    remove_knowledge_base_index(knowledge_base_id)
    write_audit(
        db,
        current_user.id,
        "delete_knowledge_base",
        f"kb_id={knowledge_base_id}",
        request=http_request,
    )

    return {
        "message": "知识库删除成功",
        "knowledge_base_id": knowledge_base_id,
    }


@app.get("/knowledge-bases/{knowledge_base_id}/index-status")
def knowledge_base_index_status(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_user_knowledge_base(knowledge_base_id, current_user, db)

    documents = db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base_id
    ).order_by(Document.id.desc()).all()

    pending = [
        d for d in documents if d.status in {"pending", "indexing"}
    ]

    return {
        "knowledge_base_id": knowledge_base_id,
        "rebuilding": is_rebuilding(knowledge_base_id),
        "index_exists": knowledge_base_index_exists(knowledge_base_id),
        "ready": not pending and (
            not documents or knowledge_base_index_exists(knowledge_base_id)
        ),
        "documents": [_document_dict(d) for d in documents],
    }


# =========================
# 文档管理（上传 / 列表 / 删除）
# =========================

ALLOWED_DOCUMENT_EXTENSIONS = {".txt", ".md", ".csv"}


@app.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    dependencies=[Depends(rate_limit)],
)
async def upload_document(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_user_knowledge_base(knowledge_base_id, current_user, db)

    original_name = os.path.basename(file.filename or "").strip()
    _, extension = os.path.splitext(original_name.lower())

    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="目前只支持 TXT / Markdown / CSV 文件",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大支持 {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB",
        )

    kb_dir = os.path.join("uploads", f"kb_{knowledge_base_id}")
    os.makedirs(kb_dir, exist_ok=True)

    file_path = os.path.join(
        kb_dir, f"{uuid.uuid4().hex}_{original_name}"
    )
    with open(file_path, "wb") as f:
        f.write(content)

    document = Document(
        filename=original_name,
        file_path=file_path,
        size=len(content),
        status="pending",
        knowledge_base_id=knowledge_base_id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    schedule_rebuild(knowledge_base_id)

    return {
        **_document_dict(document),
        "message": "文件上传成功，正在后台建立索引",
    }


@app.get("/knowledge-bases/{knowledge_base_id}/documents")
def get_documents(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_user_knowledge_base(knowledge_base_id, current_user, db)

    documents = db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base_id
    ).order_by(Document.id.desc()).all()

    return [_document_dict(d) for d in documents]


@app.delete(
    "/knowledge-bases/{knowledge_base_id}/documents/{document_id}"
)
def delete_document(
    knowledge_base_id: int,
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_user_knowledge_base(knowledge_base_id, current_user, db)

    document = db.query(Document).filter(
        Document.id == document_id,
        Document.knowledge_base_id == knowledge_base_id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    if document.file_path and os.path.exists(document.file_path):
        os.remove(document.file_path)

    db.delete(document)
    db.commit()

    schedule_rebuild(knowledge_base_id)

    return {"message": "文档删除成功", "document_id": document_id}


# =========================
# 会话管理
# =========================

@app.post("/conversations", dependencies=[Depends(rate_limit)])
def create_conversation(
    request: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_user_knowledge_base(request.knowledge_base_id, current_user, db)

    conversation = Conversation(
        title=request.title,
        user_id=current_user.id,
        knowledge_base_id=request.knowledge_base_id,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_dict(conversation)


@app.get("/conversations")
def get_conversations(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_user_knowledge_base(knowledge_base_id, current_user, db)

    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id,
        Conversation.knowledge_base_id == knowledge_base_id,
    ).order_by(Conversation.id.desc()).all()

    return [_conversation_dict(c) for c in conversations]


@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")

    total = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).count()

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.id.asc()).offset(offset).limit(min(limit, 200)).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "messages": [_message_dict(m) for m in messages],
    }


@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")

    db.delete(conversation)
    db.commit()

    return {"message": "会话删除成功", "conversation_id": conversation_id}


# =========================
# AI 对话
# =========================

def _load_chat_context(
    request: ChatRequest, user: User, db: Session
):
    """校验会话与知识库归属，返回 conversation 与历史消息。"""
    conversation = db.query(Conversation).filter(
        Conversation.id == request.conversation_id,
        Conversation.user_id == user.id,
        Conversation.knowledge_base_id == request.knowledge_base_id,
    ).first()
    if not conversation:
        raise HTTPException(
            status_code=404, detail="会话不存在，或该会话不属于当前用户"
        )

    get_user_knowledge_base(request.knowledge_base_id, user, db)

    history_rows = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(Message.id.desc()).limit(settings.HISTORY_MESSAGES).all()
    history_rows.reverse()

    history = [
        {"role": message.role, "content": message.content}
        for message in history_rows
    ]

    return conversation, history


@app.post("/chat", dependencies=[Depends(rate_limit)])
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation, history = _load_chat_context(request, current_user, db)
    kb_model, kb_index, kb_chunks, kb_sources = _load_kb_or_503(
        request.knowledge_base_id
    )

    user_message = Message(
        role="user",
        content=request.message,
        conversation_id=conversation.id,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    tool_call_log = []
    start = time.perf_counter()

    try:
        answer = agent(
            get_client(),
            request.message,
            kb_model,
            kb_index,
            kb_chunks,
            history,
            tool_call_log=tool_call_log,
            sources=kb_sources,
        )
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    latency_ms = int((time.perf_counter() - start) * 1000)

    assistant_message = Message(
        role="assistant",
        content=answer,
        conversation_id=conversation.id,
        sources=json.dumps(_extract_sources(tool_call_log), ensure_ascii=False),
        tool_calls=json.dumps(
            _strip_tool_log(tool_call_log), ensure_ascii=False
        ),
        latency_ms=latency_ms,
    )
    db.add(assistant_message)
    conversation.updated_at = utcnow()
    db.commit()
    db.refresh(assistant_message)

    return {
        "conversation_id": conversation.id,
        "message_id": assistant_message.id,
        "answer": answer,
        "sources": json.loads(assistant_message.sources or "[]"),
        "latency_ms": latency_ms,
    }


def _extract_sources(tool_call_log):
    from agent import _extract_sources as extract

    return extract(tool_call_log)


def _strip_tool_log(tool_call_log):
    return [
        {
            "round": step.get("round"),
            "tool": step.get("tool"),
            "arguments": step.get("arguments"),
            "result": str(step.get("result", ""))[:500],
        }
        for step in tool_call_log
    ]


@app.post("/chat/stream", dependencies=[Depends(rate_limit)])
def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation, history = _load_chat_context(request, current_user, db)

    user_message = Message(
        role="user",
        content=request.message,
        conversation_id=conversation.id,
    )
    db.add(user_message)
    db.commit()

    knowledge_base_id = request.knowledge_base_id
    conversation_id = conversation.id
    user_id = current_user.id

    def event_generator():
        stream_db = SessionLocal()
        try:
            try:
                kb_model, kb_index, kb_chunks, kb_sources = (
                    _load_kb_or_503(knowledge_base_id)
                )
            except HTTPException as exc:
                yield _sse({"type": "error", "message": exc.detail})
                return

            answer_parts = []
            sources = []
            tool_calls = []
            start = time.perf_counter()

            try:
                for event in agent_stream(
                    get_client(),
                    request.message,
                    kb_model,
                    kb_index,
                    kb_chunks,
                    history,
                    sources=kb_sources,
                ):
                    if event["type"] == "delta":
                        answer_parts.append(event["content"])
                        yield _sse(
                            {"type": "delta", "content": event["content"]}
                        )
                    elif event["type"] == "done":
                        sources = event.get("sources", [])
                        tool_calls = event.get("tool_calls", [])
                    else:
                        yield _sse(event)
            except Exception as exc:
                logger.exception("流式对话失败")
                yield _sse(
                    {"type": "error", "message": f"模型调用失败：{exc}"}
                )

            answer = "".join(answer_parts)
            latency_ms = int((time.perf_counter() - start) * 1000)

            if answer:
                assistant_message = Message(
                    role="assistant",
                    content=answer,
                    conversation_id=conversation_id,
                    sources=json.dumps(sources, ensure_ascii=False),
                    tool_calls=json.dumps(
                        _strip_tool_log(tool_calls), ensure_ascii=False
                    ),
                    latency_ms=latency_ms,
                )
                stream_db.add(assistant_message)
                conversation_row = stream_db.query(Conversation).filter(
                    Conversation.id == conversation_id
                ).first()
                if conversation_row:
                    conversation_row.updated_at = utcnow()
                stream_db.commit()

                yield _sse(
                    {
                        "type": "done",
                        "answer": answer,
                        "sources": sources,
                        "latency_ms": latency_ms,
                    }
                )
            else:
                yield _sse(
                    {
                        "type": "done",
                        "answer": "",
                        "sources": [],
                        "latency_ms": latency_ms,
                    }
                )
        finally:
            stream_db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# =========================
# Coding Agent（默认关闭，且仅管理员可用）
# =========================

@app.post("/coding-agent", dependencies=[Depends(rate_limit)])
def coding_agent(
    request: CodingAgentRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if not settings.CODING_AGENT_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Coding Agent 未启用。请在服务端设置 "
            "CODING_AGENT_ENABLED=true 开启。",
        )

    model, index, chunks, sources = get_default_knowledge()

    result = run_coding_agent(
        client=get_client(),
        task=request.task.strip(),
        model=model,
        index=index,
        chunks=chunks,
        max_rounds=15,
    )

    write_audit(
        db,
        current_user.id,
        "coding_agent",
        request.task.strip()[:200],
    )

    return result


def _cleanup_resources():
    from database import engine
    from indexing import shutdown

    try:
        shutdown()
    except Exception:
        pass
    try:
        engine.dispose()
    except Exception:
        pass


atexit.register(_cleanup_resources)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
