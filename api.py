from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel
from sqlalchemy.orm import Session
from rag import load_knowledge_base_index
import os
import uuid
from database import (
    get_db,
    User,
    KnowledgeBase,
    Conversation,
    Message,
    Document
)

from rag import save_knowledge_base_index

from rag import (
    load_documents,
    split_by_paragraph,
    load_embedding_model,
    create_embeddings,
    build_index,
)

from agent import (
    create_client,
    agent,
)


# =========================
# FastAPI
# =========================

app = FastAPI(
    title="AI Agent SaaS API",
    description="RAG + Tool Calling + Agent + SaaS",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 密码加密
# =========================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# =========================
# JWT 配置
# =========================
SECRET_KEY = "simple-rag-secret-key"
ALGORITHM = "HS256"

# Access Token 有效期：60分钟
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Refresh Token 有效期：7天
REFRESH_TOKEN_EXPIRE_DAYS = 7
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        token_type = payload.get("type")

        if token_type != "access":
            raise HTTPException(
                status_code=401,
                detail="无效的 Access Token"
            )
        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Token 中没有用户信息"
            )

        user = db.query(User).filter(
            User.id == int(user_id)
        ).first()

        if not user:
            raise HTTPException(
                status_code=401,
                detail="用户不存在"
            )

        return user

    except Exception as e:
        print("JWT 验证错误：", e)
        raise HTTPException(
            status_code=401,
            detail=f"Token 验证失败：{str(e)}"
        )
# =========================
# 初始化 AI Agent
# =========================

print("正在加载知识库...")

text = load_documents("data/knowledge.txt")

chunks = split_by_paragraph(text)

print(f"知识库 Chunk 数量：{len(chunks)}")

print("正在加载 Embedding 模型...")

model = load_embedding_model()

print("正在生成 Embedding...")

embeddings = create_embeddings(model, chunks)

print("正在建立 FAISS 索引...")

index = build_index(embeddings)

print("正在创建 DeepSeek 客户端...")

client = create_client()

print("AI Agent 初始化完成！")


# =========================
# 请求模型
# =========================

class ChatRequest(BaseModel):
    message: str
    conversation_id: int
    knowledge_base_id: int


class UserCreate(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""



class ConversationCreate(BaseModel):
    title: str
    knowledge_base_id: int
   


# =========================
# 健康检查
# =========================

@app.get("/health")
def health():
    return {
        "status": "ok"
    }


# =========================
# AI 对话
# =========================

@app.post("/chat")
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):


    # 查询会话
    conversation = db.query(Conversation).filter(
    Conversation.id == request.conversation_id,
    Conversation.user_id == current_user.id,
    Conversation.knowledge_base_id == request.knowledge_base_id
).first()

    if not conversation:
        return {
            "error": "会话不存在，或者该会话不属于当前用户"
        }
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == request.knowledge_base_id,
        KnowledgeBase.user_id == current_user.id
    ).first()

    if not knowledge_base:
        return {
            "error": "知识库不存在，或者该知识库不属于当前用户"
        }

    try:
        kb_model, kb_index, kb_chunks = load_knowledge_base_index(
            request.knowledge_base_id
        )
    except FileNotFoundError as e:
        return {
            "error": str(e)
        }

    history_messages = db.query(Message).filter(
        Message.conversation_id == conversation.id
    ).order_by(
        Message.id.desc()
    ).limit(10).all()

    history_messages.reverse()

    history = []

    for message in history_messages:
        history.append({
            "role": message.role,
            "content": message.content
        })


    # 调用 Agent
    answer = agent(
    client,
    request.message,
    kb_model,
    kb_index,
    kb_chunks,
    history
)

    # 保存用户消息
    user_message = Message(
        role="user",
        content=request.message,
        conversation_id=conversation.id
    )

    db.add(user_message)

    # 保存 AI 消息
    assistant_message = Message(
        role="assistant",
        content=answer,
        conversation_id=conversation.id
    )

    db.add(assistant_message)

    # 提交数据库
    db.commit()

    return {
    "user_id": current_user.id,
    "conversation_id": conversation.id,
    "message": request.message,
    "answer": answer
}


# =========================
# 创建用户
# =========================

@app.post("/users")
def create_user(
    request: UserCreate,
    db: Session = Depends(get_db)
):

    hashed_password = pwd_context.hash(
        request.password
    )

    user = User(
        username=request.username,
        password=hashed_password
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "username": user.username
    }

# =========================
# 用户登录
# =========================

@app.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):

    # 查询用户
    user = db.query(User).filter(
        User.username == request.username
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误"
        )

    # 验证密码
    if not pwd_context.verify(
        request.password,
        user.password
    ):
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误"
        )

    # =========================
    # 创建 Access Token
    # =========================

    access_expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    access_payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": access_expire,
        "type": "access"
    }

    access_token = jwt.encode(
        access_payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    # =========================
    # 创建 Refresh Token
    # =========================

    refresh_expire = datetime.utcnow() + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    refresh_payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": refresh_expire,
        "type": "refresh"
    }

    refresh_token = jwt.encode(
        refresh_payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": user.id
    }


# =========================
# 刷新 Access Token
# =========================

@app.post("/refresh")
def refresh_access_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):

    try:
        payload = jwt.decode(
            request.refresh_token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        # 必须是 Refresh Token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401,
                detail="无效的 Refresh Token"
            )

        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Refresh Token 中没有用户信息"
            )

        # 查询用户
        user = db.query(User).filter(
            User.id == int(user_id)
        ).first()

        if not user:
            raise HTTPException(
                status_code=401,
                detail="用户不存在"
            )

        # 创建新的 Access Token
        access_expire = datetime.utcnow() + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

        access_payload = {
            "sub": str(user.id),
            "username": user.username,
            "exp": access_expire,
            "type": "access"
        }

        access_token = jwt.encode(
            access_payload,
            SECRET_KEY,
            algorithm=ALGORITHM
        )

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Refresh Token 验证错误：", e)

        raise HTTPException(
            status_code=401,
            detail="Refresh Token 已过期或无效"
        )


    # =========================
    # 创建 Access Token
    # =========================

    access_expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    access_payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": access_expire,
        "type": "access"
    }

    access_token = jwt.encode(
        access_payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    # =========================
    # 创建 Refresh Token
    # =========================

    refresh_expire = datetime.utcnow() + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    refresh_payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": refresh_expire,
        "type": "refresh"
    }

    refresh_token = jwt.encode(
        refresh_payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    # 返回两个 Token
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": user.id
    }
# =========================
# 创建知识库
# =========================

@app.post("/knowledge-bases")
def create_knowledge_base(
    request: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    knowledge_base = KnowledgeBase(
    name=request.name,
    description=request.description,
    user_id=current_user.id
)

    db.add(knowledge_base)
    db.commit()
    db.refresh(knowledge_base)

    return {
        "id": knowledge_base.id,
        "name": knowledge_base.name,
        "description": knowledge_base.description,
        "user_id": knowledge_base.user_id
    }

@app.get("/knowledge-bases")
def get_knowledge_bases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    knowledge_bases = db.query(KnowledgeBase).filter(
        KnowledgeBase.user_id == current_user.id
    ).order_by(
        KnowledgeBase.id.desc()
    ).all()

    return [
        {
            "id": knowledge_base.id,
            "name": knowledge_base.name,
            "description": knowledge_base.description,
            "user_id": knowledge_base.user_id
        }
        for knowledge_base in knowledge_bases
    ]

@app.delete("/knowledge-bases/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. 检查知识库是否属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.user_id == current_user.id
    ).first()

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="知识库不存在"
        )

    # 2. 先查询这个知识库下的所有文档
    documents = db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base_id
    ).all()

    # 3. 删除实际上传的文件
    for document in documents:
        if document.file_path and os.path.exists(document.file_path):
            os.remove(document.file_path)

    # 4. 删除数据库中的文档记录
    db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base_id
    ).delete()

    # 5. 删除知识库
    db.delete(knowledge_base)

    # 6. 提交数据库
    db.commit()

    # 7. 删除 FAISS 索引文件
    index_path = f"indexes/kb_{knowledge_base_id}.index"
    chunks_path = f"indexes/kb_{knowledge_base_id}_chunks.json"

    if os.path.exists(index_path):
        os.remove(index_path)

    if os.path.exists(chunks_path):
        os.remove(chunks_path)

    return {
        "message": "知识库删除成功",
        "knowledge_base_id": knowledge_base_id
    }
# =========================
# 创建对话
# =========================

@app.post("/conversations")
def create_conversation(
    request: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == request.knowledge_base_id,
        KnowledgeBase.user_id == current_user.id
    ).first()

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="知识库不存在"
        )

    conversation = Conversation(
        title=request.title,
        user_id=current_user.id,
        knowledge_base_id=request.knowledge_base_id
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return {
        "id": conversation.id,
        "title": conversation.title,
        "user_id": conversation.user_id,
        "knowledge_base_id": conversation.knowledge_base_id
    }

@app.get("/conversations")
def get_conversations(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id,
        Conversation.knowledge_base_id == knowledge_base_id
    ).order_by(
        Conversation.id.desc()
    ).all()

    return [
        {
            "id": conversation.id,
            "title": conversation.title,
            "user_id": conversation.user_id,
            "knowledge_base_id": conversation.knowledge_base_id
        }
        for conversation in conversations
    ]



@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. 检查会话是否属于当前用户
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="会话不存在"
        )

    # 2. 查询这个会话的所有消息
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(
        Message.id.asc()
    ).all()

    # 3. 返回消息
    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content
        }
        for message in messages
    ]

@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. 检查会话是否属于当前用户
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="会话不存在"
        )

    # 2. 删除这个会话下面的所有消息
    db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).delete()

    # 3. 删除会话
    db.delete(conversation)

    # 4. 提交数据库
    db.commit()

    return {
        "message": "会话删除成功",
        "conversation_id": conversation_id
    }
# =========================
# 知识库文档管理（上传 / 列表 / 删除）
# =========================

UPLOAD_DIR = "uploads"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 单个文件最大 10MB


def get_user_knowledge_base(
    knowledge_base_id: int,
    current_user: User,
    db: Session
):
    """获取属于当前用户的知识库，不存在则返回 404"""
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.user_id == current_user.id
    ).first()

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="知识库不存在"
        )

    return knowledge_base


def rebuild_knowledge_base_index(knowledge_base_id: int, db: Session):
    """根据知识库当前所有文档重建 FAISS 索引；没有文档时清理索引文件"""
    documents = db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base_id
    ).all()

    file_paths = [doc.file_path for doc in documents]

    if not file_paths:
        for path in (
            f"indexes/kb_{knowledge_base_id}.index",
            f"indexes/kb_{knowledge_base_id}_chunks.json",
        ):
            if os.path.exists(path):
                os.remove(path)
        return

    save_knowledge_base_index(
        knowledge_base_id,
        file_paths
    )


# ---------- 上传文档 ----------

@app.post("/knowledge-bases/{knowledge_base_id}/documents")
async def upload_document(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. 检查知识库是否属于当前用户
    get_user_knowledge_base(knowledge_base_id, current_user, db)

    # 2. 清理文件名，防止路径穿越；目前只支持 TXT
    original_name = os.path.basename(file.filename or "")

    if not original_name.lower().endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="目前只支持 TXT 文件"
        )

    # 3. 读取并校验内容
    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="文件内容为空"
        )

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail="文件过大，最大支持 10MB"
        )

    # 4. 按知识库分目录，文件名加 UUID 前缀，避免同名覆盖
    kb_dir = os.path.join(UPLOAD_DIR, f"kb_{knowledge_base_id}")
    os.makedirs(kb_dir, exist_ok=True)

    file_path = os.path.join(
        kb_dir,
        f"{uuid.uuid4().hex}_{original_name}"
    )

    with open(file_path, "wb") as f:
        f.write(content)

    # 5. 保存数据库记录
    document = Document(
        filename=original_name,
        file_path=file_path,
        knowledge_base_id=knowledge_base_id
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    # 6. 重建 FAISS 索引；失败则回滚文档记录和文件
    try:
        rebuild_knowledge_base_index(knowledge_base_id, db)
    except Exception as e:
        print("建立索引失败：", e)

        db.delete(document)
        db.commit()

        if os.path.exists(file_path):
            os.remove(file_path)

        raise HTTPException(
            status_code=500,
            detail=f"文档处理失败：{str(e)}"
        )

    return {
        "id": document.id,
        "filename": document.filename,
        "knowledge_base_id": document.knowledge_base_id,
        "message": "文件上传成功"
    }


# ---------- 文档列表 ----------

@app.get("/knowledge-bases/{knowledge_base_id}/documents")
def get_documents(
    knowledge_base_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    get_user_knowledge_base(knowledge_base_id, current_user, db)

    documents = db.query(Document).filter(
        Document.knowledge_base_id == knowledge_base_id
    ).order_by(
        Document.id.desc()
    ).all()

    return [
        {
            "id": document.id,
            "filename": document.filename,
            "knowledge_base_id": document.knowledge_base_id
        }
        for document in documents
    ]


# ---------- 删除单个文档 ----------

@app.delete("/knowledge-bases/{knowledge_base_id}/documents/{document_id}")
def delete_document(
    knowledge_base_id: int,
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    get_user_knowledge_base(knowledge_base_id, current_user, db)

    document = db.query(Document).filter(
        Document.id == document_id,
        Document.knowledge_base_id == knowledge_base_id
    ).first()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="文档不存在"
        )

    # 删除实际文件
    if document.file_path and os.path.exists(document.file_path):
        os.remove(document.file_path)

    # 删除数据库记录
    db.delete(document)
    db.commit()

    # 用剩余文档重建索引
    rebuild_knowledge_base_index(knowledge_base_id, db)

    return {
        "message": "文档删除成功",
        "document_id": document_id
    }