from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from app.core.config import ROOT_DIR


def configure_logging(
    *,
    level: int = logging.INFO,
    log_dir: Path | None = None,
    log_filename: str = "agenthub.log",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """配置统一的后端日志系统，输出到控制台和文件。

    所有日志（含 uvicorn、FastAPI 及第三方库）统一由根日志记录器处理，
    避免控制台重复输出，同时全部落入文件。
    """
    log_format = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # 文件输出（按大小轮转）
    if log_dir is None:
        log_dir = ROOT_DIR / "backend" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / log_filename

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有 handler，统一接管
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # 清除 uvicorn 自带 handler，让其走根 logger，避免控制台重复
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        for handler in uvicorn_logger.handlers[:]:
            uvicorn_logger.removeHandler(handler)
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)

    # 降低部分第三方库的日志级别，避免噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("日志系统已初始化，文件: %s", log_file)
