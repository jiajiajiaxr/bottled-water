from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from app.core.config import ROOT_DIR


def _make_log_dir() -> Path:
    """返回并确保日志目录存在。"""
    log_dir = ROOT_DIR / "backend" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def configure_logging(
    *,
    level: int = logging.INFO,
    log_dir: Path | None = None,
) -> None:
    """配置统一的后端日志系统，输出到控制台和文件。

    所有日志（含 uvicorn、FastAPI 及第三方库）统一由根日志记录器处理，
    避免控制台重复输出，同时全部落入文件。

    后端日志写入 application-YYYY-MM-DD.log，按日期轮转，保留 30 天。
    """
    log_format = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    log_dir = log_dir or _make_log_dir()
    backend_log = log_dir / "application.log"

    backend_handler = logging.handlers.TimedRotatingFileHandler(
        backend_log,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    backend_handler.suffix = "%Y-%m-%d"
    backend_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(backend_handler)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        for handler in uvicorn_logger.handlers[:]:
            uvicorn_logger.removeHandler(handler)
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("后端日志系统已初始化，文件: %s", backend_log)


_frontend_logger: logging.Logger | None = None


def get_frontend_logger() -> logging.Logger:
    """返回前端日志记录器，懒加载。

    前端日志写入 frontend-YYYY-MM-DD.log，按日期轮转，保留 30 天。
    与后端 application-YYYY-MM-DD.log 完全隔离。
    """
    global _frontend_logger
    if _frontend_logger is not None:
        return _frontend_logger

    log_format = "[%(asctime)s] [%(levelname)s] [frontend] %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    log_dir = _make_log_dir()
    frontend_log = log_dir / "frontend.log"

    handler = logging.handlers.TimedRotatingFileHandler(
        frontend_log,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(formatter)

    logger = logging.getLogger("frontend")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)

    _frontend_logger = logger
    return logger
