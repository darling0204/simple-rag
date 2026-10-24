"""数据库模型与轻量级迁移。

使用 SQLAlchemy + SQLite，启动时自动执行增量迁移：
为旧库补充新列，保留已有数据。生产环境可替换为 PostgreSQL
（只需修改 DATABASE_URL 环境变量）。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship,
)

from config import settings


def utcnow():
    """返回无时区信息的 UTC 时间，避免 SQLite 时区比较问题。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine_kwargs = {}
if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """启用 SQLite 外键约束，保证级联删除生效。"""
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(100), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    knowledge_bases = relationship(
        "KnowledgeBase", back_populates="user"
    )
    conversations = relationship(
        "Conversation", back_populates="user"
    )


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), default="")
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user = relationship("User", back_populates="knowledge_bases")
    documents = relationship(
        "Document",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    conversations = relationship(
        "Conversation",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    size = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    # pending / indexing / ready / failed
    status = Column(String(20), default="pending", index=True)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow, nullable=False)
    knowledge_base_id = Column(
        Integer, ForeignKey("knowledge_bases.id"), index=True
    )

    knowledge_base = relationship(
        "KnowledgeBase", back_populates="documents"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    knowledge_base_id = Column(
        Integer, ForeignKey("knowledge_bases.id"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user = relationship("User", back_populates="conversations")
    knowledge_base = relationship(
        "KnowledgeBase", back_populates="conversations"
    )
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(Text, default="[]")
    tool_calls = Column(Text, default="[]")
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id"), index=True
    )

    conversation = relationship("Conversation", back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    detail = Column(Text, default="")
    ip_address = Column(String(64), default="")
    created_at = Column(DateTime, default=utcnow, nullable=False)


# =========================
# 轻量级迁移：为旧库补充新列
# =========================

_MIGRATIONS = {
    "users": [
        ("is_admin", "BOOLEAN NOT NULL DEFAULT 0"),
        ("created_at", "DATETIME"),
    ],
    "knowledge_bases": [
        ("created_at", "DATETIME"),
        ("updated_at", "DATETIME"),
    ],
    "documents": [
        ("size", "INTEGER DEFAULT 0"),
        ("chunk_count", "INTEGER DEFAULT 0"),
        ("status", "VARCHAR(20) DEFAULT 'pending'"),
        ("error_message", "TEXT DEFAULT ''"),
        ("created_at", "DATETIME"),
    ],
    "conversations": [
        ("created_at", "DATETIME"),
        ("updated_at", "DATETIME"),
    ],
    "messages": [
        ("sources", "TEXT DEFAULT '[]'"),
        ("tool_calls", "TEXT DEFAULT '[]'"),
        ("latency_ms", "INTEGER DEFAULT 0"),
        ("created_at", "DATETIME"),
    ],
}


def run_migrations():
    """创建缺失的表并为旧表补充新列。"""
    Base.metadata.create_all(bind=engine)

    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        documents_got_created_at = False

        for table_name, columns in _MIGRATIONS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {
                col["name"] for col in inspector.get_columns(table_name)
            }
            for column_name, column_ddl in columns:
                if column_name not in existing_columns:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN {column_name} {column_ddl}"
                        )
                    )
                    if (
                        table_name == "documents"
                        and column_name == "created_at"
                    ):
                        documents_got_created_at = True

        # 迁移旧数据：升级前就存在的文档视为索引已完成
        if documents_got_created_at:
            conn.execute(
                text(
                    "UPDATE documents "
                    "SET status = 'ready', created_at = CURRENT_TIMESTAMP "
                    "WHERE created_at IS NULL"
                )
            )

        conn.execute(
            text(
                "UPDATE users SET is_admin = 0 "
                "WHERE is_admin IS NULL"
            )
        )

        # 若没有任何管理员，将最早注册的用户提升为管理员
        has_admin = conn.execute(
            text("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        ).scalar()
        if not has_admin:
            conn.execute(
                text(
                    "UPDATE users SET is_admin = 1 "
                    "WHERE id = (SELECT MIN(id) FROM users)"
                )
            )


def get_db():
    """FastAPI 依赖：每个请求一个独立会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
