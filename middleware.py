"""HTTP 中间件：请求 ID、访问日志与错误处理。"""

import contextvars
import time
import traceback
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import logging


request_id_var: contextvars.ContextVar = contextvars.ContextVar(
    "request_id", default="-"
)

access_logger = logging.getLogger("nova.access")
error_logger = logging.getLogger("nova.error")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 request_id，并记录访问日志。"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        start = time.monotonic()

        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.monotonic() - start) * 1000)
            access_logger.warning(
                "%s %s -> 500 (%dms)",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        finally:
            request_id_var.reset(token)

        duration_ms = int((time.monotonic() - start) * 1000)
        response.headers["X-Request-ID"] = request_id
        access_logger.info(
            "%s %s -> %s (%dms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "-")
    error_logger.error(
        "Unhandled error | %s\n%s",
        request_id,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误，请稍后再试",
            "request_id": request_id,
        },
    )
