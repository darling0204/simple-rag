"""安全相关：密码哈希、JWT、身份依赖与内存限流器。"""

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from database import User, get_db


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except Exception:
        return False


def _base_payload(user: User, token_type: str):
    now = datetime.now(timezone.utc)
    return {
        "sub": str(user.id),
        "username": user.username,
        "iat": now,
        "type": token_type,
    }


def create_access_token(user: User) -> tuple[str, datetime]:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = _base_payload(user, "access")
    payload["exp"] = expire
    token = jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return token, expire


def create_refresh_token(user: User) -> tuple[str, datetime]:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = _base_payload(user, "refresh")
    payload["exp"] = expire
    token = jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return token, expire


def decode_token(token: str, expected_type: str) -> dict:
    """解码并校验 Token，失败抛 HTTPException(401)。"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail="登录状态已失效，请重新登录",
        ) from exc

    if payload.get("type") != expected_type:
        raise HTTPException(
            status_code=401,
            detail="Token 类型无效",
        )

    if payload.get("sub") is None:
        raise HTTPException(
            status_code=401,
            detail="Token 中没有用户信息",
        )

    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI 依赖：从 Authorization 头解析当前用户。"""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="未登录，请先登录",
        )

    payload = decode_token(credentials.credentials, "access")

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Token 无效",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=401,
            detail="用户不存在",
        )

    return user


def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="该操作需要管理员权限",
        )
    return current_user


# =========================
# 内存滑动窗口限流器
# =========================

class SlidingWindowRateLimiter:
    """按 key（用户 id 或 IP）做滑动窗口限流，线程安全。"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            window = self._hits[key]
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= self.max_requests:
                return False
            window.append(now)
            return True

    def cleanup(self):
        """定期清理过期 key，防止内存无限增长。"""
        cutoff = time.monotonic() - self.window_seconds * 2
        with self._lock:
            stale = [
                key
                for key, window in self._hits.items()
                if not window or window[-1] <= cutoff
            ]
            for key in stale:
                del self._hits[key]


_limiter = SlidingWindowRateLimiter(
    settings.RATE_LIMIT_REQUESTS,
    settings.RATE_LIMIT_WINDOW_SECONDS,
)


def rate_limit(request: Request):
    """FastAPI 依赖：按用户或 IP 限流。"""
    if not settings.RATE_LIMIT_ENABLED:
        return

    key = f"ip:{request.client.host if request.client else 'unknown'}"

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        try:
            payload = decode_token(auth_header[7:], "access")
            key = f"user:{payload.get('sub', 'unknown')}"
        except HTTPException:
            key = f"ip:{request.client.host if request.client else 'unknown'}"

    if not _limiter.allow(key):
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后再试",
        )
