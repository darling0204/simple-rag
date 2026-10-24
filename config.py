"""应用配置中心：所有可配置项都支持通过环境变量覆盖。

环境变量说明见项目根目录的 .env.example。
"""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: str) -> list:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    """全局配置，单例模式。"""

    # ---- 应用 ----
    APP_NAME: str = "Nova Agent API"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = os.getenv("APP_ENV", "development")

    # ---- 安全 ----
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "dev-only-secret-key-please-override-in-production",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _env_int(
        "ACCESS_TOKEN_EXPIRE_MINUTES", 60
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = _env_int(
        "REFRESH_TOKEN_EXPIRE_DAYS", 7
    )
    CORS_ORIGINS: list = _env_list(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://134.175.20.148",
    )

    # ---- 数据库 ----
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'ai_agent.db').as_posix()}",
    )

    # ---- LLM ----
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    LLM_TIMEOUT_SECONDS: int = _env_int("LLM_TIMEOUT_SECONDS", 120)
    LLM_MAX_RETRIES: int = _env_int("LLM_MAX_RETRIES", 2)

    # ---- RAG ----
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    TOP_K: int = _env_int("TOP_K", 4)
    CHUNK_SIZE: int = _env_int("CHUNK_SIZE", 500)
    CHUNK_OVERLAP: int = _env_int("CHUNK_OVERLAP", 60)

    # ---- 业务限制 ----
    MAX_UPLOAD_SIZE: int = _env_int("MAX_UPLOAD_SIZE_MB", 10) * 1024 * 1024
    MAX_MESSAGE_LENGTH: int = _env_int("MAX_MESSAGE_LENGTH", 8000)
    HISTORY_MESSAGES: int = _env_int("HISTORY_MESSAGES", 12)

    # ---- Coding Agent（默认关闭，防止任意代码执行） ----
    CODING_AGENT_ENABLED: bool = _env_bool("CODING_AGENT_ENABLED", False)

    # ---- 限流 ----
    RATE_LIMIT_ENABLED: bool = _env_bool("RATE_LIMIT_ENABLED", True)
    RATE_LIMIT_REQUESTS: int = _env_int("RATE_LIMIT_REQUESTS", 60)
    RATE_LIMIT_WINDOW_SECONDS: int = _env_int(
        "RATE_LIMIT_WINDOW_SECONDS", 60
    )

    # ---- 日志 ----
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_DIR: Path = Path(os.getenv("LOG_DIR", BASE_DIR / "logs"))


settings = Settings()

# 兼容旧代码的模块级导入
TOP_K = settings.TOP_K
CHUNK_SIZE = settings.CHUNK_SIZE
CHUNK_OVERLAP = settings.CHUNK_OVERLAP
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
LLM_MODEL = settings.LLM_MODEL
DEEPSEEK_BASE_URL = settings.DEEPSEEK_BASE_URL
