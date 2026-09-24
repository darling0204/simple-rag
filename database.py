from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship


# =========================
# 数据库配置
# =========================

DATABASE_URL = "sqlite:///./ai_agent.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


# =========================
# 用户表
# =========================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    password = Column(String(100))

    knowledge_bases = relationship(
        "KnowledgeBase",
        back_populates="user"
    )

    conversations = relationship(
        "Conversation",
        back_populates="user"
    )


# =========================
# 知识库表
# =========================

class KnowledgeBase(Base):
   
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    description = Column(String(255))

    user_id = Column(
        Integer,
        ForeignKey("users.id")
    )

    user = relationship(
        "User",
        back_populates="knowledge_bases"
    )
    documents = relationship(
        "Document",
        back_populates="knowledge_base"
    )

    conversations = relationship(
    "Conversation",
    back_populates="knowledge_base"
)
# =========================
# 知识库文档表
# =========================

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String(255))

    file_path = Column(String(500))

    knowledge_base_id = Column(
        Integer,
        ForeignKey("knowledge_bases.id")
    )

    knowledge_base = relationship(
        "KnowledgeBase",
        back_populates="documents"
    )

# =========================
# 对话表
# =========================

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))

    user_id = Column(
        Integer,
        ForeignKey("users.id")
    )

    knowledge_base_id = Column(
        Integer,
        ForeignKey("knowledge_bases.id"),
        nullable=True
    )

    user = relationship(
        "User",
        back_populates="conversations"
    )

    knowledge_base = relationship(
        "KnowledgeBase",
        back_populates="conversations"
    )

    messages = relationship(
        "Message",
        back_populates="conversation"
    )


# =========================
# 消息表
# =========================

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(20))
    content = Column(Text)

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id")
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages"
    )


# =========================
# 创建数据库表
# =========================

Base.metadata.create_all(bind=engine)


# =========================
# 获取数据库连接
# =========================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()