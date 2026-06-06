from __future__ import annotations

import mimetypes
import re
from datetime import datetime
from pathlib import Path


ROOT_LABELS = {
    "uploads": "上传文件",
    "artifacts": "产物文件",
    "sandbox": "沙箱文件",
    "exports": "导出文件",
    "projects": "项目文件",
    "files": "兼容文件",
    "tools": "工具文件",
    "logs": "日志文件",
    "conversations": "按会话归档",
    "agents": "Agent 输出",
    "tasks": "任务输出",
    "legacy": "历史文件",
}

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
HIDDEN_PREFIXES = ("~$", ".~", ".tmp", "tmp-")
HIDDEN_SUFFIXES = (".tmp", ".temp", ".part", ".crdownload")


def display_name(name: str, *, fallback_name: str | None = None, fallback_id: str = "") -> str:
    candidate = Path(str(name or "")).name.strip()
    if not candidate or UUID_PATTERN.match(Path(candidate).stem):
        suffix = Path(candidate).suffix
        readable = (fallback_name or "").strip()
        candidate = (
            f"{readable}{suffix}"
            if readable and suffix and not readable.endswith(suffix)
            else readable
        )
        if not candidate:
            candidate = f"文件 {str(fallback_id)[:8]}{suffix}"
    return candidate[:180]


def readable_segment(part: str, *, path: str = "") -> str:
    if not UUID_PATTERN.match(part):
        return ROOT_LABELS.get(part, part)
    short_id = part[:8]
    if path.startswith("artifacts/"):
        return f"产物 {short_id}"
    if path.startswith("uploads/") or path.startswith("files/"):
        return f"上传记录 {short_id}"
    if path.startswith("exports/"):
        return f"导出记录 {short_id}"
    if path.startswith("sandbox/"):
        if "/tasks/" in path:
            return f"任务运行 {short_id}"
        if "/agents/" in path:
            return f"Agent 工作区 {short_id}"
        return f"沙箱记录 {short_id}"
    if path.startswith("projects/"):
        return f"项目文件夹 {short_id}"
    return f"文件夹 {short_id}"


def duplicate_suffix(updated_at: str | None, node_id: str) -> str:
    if updated_at:
        try:
            return datetime.fromisoformat(updated_at.replace("Z", "+00:00")).strftime("%m-%d %H-%M")
        except ValueError:
            pass
    return node_id.split(":", 1)[-1][:8]


def should_hide_file(name: str, size: int | None) -> bool:
    normalized = name.lower()
    if normalized.startswith(HIDDEN_PREFIXES) or normalized.endswith(HIDDEN_SUFFIXES):
        return True
    return (size or 0) <= 0


def source_from_path(path: str, fallback: str) -> str:
    return {
        "uploads": "upload",
        "files": "legacy",
        "artifacts": "artifact",
        "sandbox": "sandbox",
        "exports": "export",
        "projects": "project",
    }.get(path.split("/", 1)[0], fallback)


def guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"
