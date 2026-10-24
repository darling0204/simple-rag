"""结构化日志配置：控制台 + 按天轮转文件。"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

from config import settings
from middleware import request_id_var


class RequestIdFilter(logging.Filter):
    """把当前请求的 request_id 注入到每条日志记录。"""

    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


def setup_logging():
    """初始化应用日志，同时收敛第三方库的噪音日志。"""
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_format = (
        "%(asctime)s | %(levelname)-7s | %(name)s | "
        "%(request_id)s | %(message)s"
    )
    formatter = logging.Formatter(log_format)
    request_filter = RequestIdFilter()

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)

    # 避免重复配置
    if any(
        getattr(handler, "_nova_marker", False)
        for handler in root.handlers
    ):
        return

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(request_filter)
    console.setLevel(settings.LOG_LEVEL)
    console._nova_marker = True
    root.addHandler(console)

    file_handler = TimedRotatingFileHandler(
        os.path.join(settings.LOG_DIR, "app.log"),
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(request_filter)
    file_handler.setLevel(settings.LOG_LEVEL)
    file_handler._nova_marker = True
    root.addHandler(file_handler)

    for noisy in (
        "uvicorn.access",
        "httpx",
        "httpcore",
        "openai",
        "sentence_transformers",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
