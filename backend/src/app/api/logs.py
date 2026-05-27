from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.logging_config import get_frontend_logger
from app.core.response import ok
from app.deps import get_current_user
from app.schemas.common import FrontendLogBatch

router = APIRouter(tags=["logs"])

_level_map: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


@router.post("/logs")
async def receive_frontend_logs(
    batch: FrontendLogBatch,
    _user=Depends(get_current_user),
):
    """接收前端批量日志，写入 frontend-YYYY-MM-DD.log。"""
    logger = get_frontend_logger()
    for entry in batch.logs:
        level = _level_map.get(entry.level.upper(), logging.INFO)
        extra_parts: list[str] = []
        if entry.url:
            extra_parts.append(f"url={entry.url}")
        if entry.data:
            extra_parts.append(f"data={entry.data}")
        extra = f" | {' | '.join(extra_parts)}" if extra_parts else ""
        logger.log(level, "[%s] %s%s", entry.module, entry.message, extra)
    return ok()
