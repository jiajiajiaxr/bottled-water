from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.tools.builtins.file.extractors import extract_text_from_path
from app.services.tools.builtins.file.converters import generate_pdf
from app.services.workspaces.filesystem import safe_segment, workspace_root

OFFICE_SUFFIXES = {".docx", ".pptx", ".xlsx"}
OFFICE_MIME_MARKERS = ("officedocument", "wordprocessingml", "presentationml", "spreadsheetml")
DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class OfficePreviewResult:
    preview_pdf_path: Path | None
    cached: bool
    error: str | None = None
    fallback_text: str = ""


def is_office_file(content_type: str, filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    normalized = content_type.lower()
    return suffix in OFFICE_SUFFIXES or any(marker in normalized for marker in OFFICE_MIME_MARKERS)


def build_office_preview(
    *,
    workspace_id: str,
    node_id: str,
    target: dict[str, Any],
    filename: str,
    mime_type: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> OfficePreviewResult:
    source = _source_file(workspace_id, node_id, target, filename, mime_type)
    preview_pdf = source.cache_dir / "preview.pdf"
    if preview_pdf.exists() and preview_pdf.stat().st_size > 0:
        return OfficePreviewResult(preview_pdf_path=preview_pdf, cached=True)

    soffice = _find_soffice()
    if not soffice:
        return _fallback_pdf(
            source.path,
            preview_pdf,
            mime_type,
            filename,
            "当前环境未安装 LibreOffice，已使用文本抽取生成 PDF 预览",
        )

    try:
        _convert_with_libreoffice(soffice, source.path, source.cache_dir, timeout_seconds)
        generated = source.cache_dir / f"{source.path.stem}.pdf"
        if generated.exists() and generated != preview_pdf:
            generated.replace(preview_pdf)
        if not preview_pdf.exists() or preview_pdf.stat().st_size <= 0:
            return _fallback_pdf(source.path, preview_pdf, mime_type, filename, "LibreOffice 未生成可用的 PDF 预览文件")
        return OfficePreviewResult(preview_pdf_path=preview_pdf, cached=False)
    except subprocess.TimeoutExpired:
        return _fallback_pdf(source.path, preview_pdf, mime_type, filename, "Office PDF 预览生成超时，已降级生成文本 PDF 预览")
    except Exception as exc:
        return _fallback_pdf(source.path, preview_pdf, mime_type, filename, f"Office PDF 预览生成失败，已降级：{exc}")


@dataclass(frozen=True)
class _SourceFile:
    path: Path
    cache_dir: Path


def _source_file(workspace_id: str, node_id: str, target: dict[str, Any], filename: str, mime_type: str) -> _SourceFile:
    source_bytes = _target_bytes(target)
    source_path = Path(str(target["path"])) if target.get("path") else None
    fingerprint = _fingerprint(node_id, source_path, source_bytes, filename, mime_type)
    cache_dir = workspace_root(workspace_id) / "previews" / fingerprint
    cache_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(filename).suffix.lower() or ".office"
    safe_name = safe_segment(Path(filename).stem or "source", default="source")
    cached_source = cache_dir / f"{safe_name}{suffix}"
    if source_path and source_path.exists():
        if not cached_source.exists() or cached_source.stat().st_mtime < source_path.stat().st_mtime:
            shutil.copyfile(source_path, cached_source)
    elif source_bytes is not None:
        if not cached_source.exists() or cached_source.read_bytes() != source_bytes:
            cached_source.write_bytes(source_bytes)
    else:
        cached_source.write_bytes(b"")

    metadata = {"node_id": node_id, "filename": filename, "mime_type": mime_type, "fingerprint": fingerprint}
    (cache_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return _SourceFile(path=cached_source, cache_dir=cache_dir)


def _target_bytes(target: dict[str, Any]) -> bytes | None:
    value = target.get("bytes")
    return value if isinstance(value, bytes) else None


def _fingerprint(
    node_id: str,
    source_path: Path | None,
    source_bytes: bytes | None,
    filename: str,
    mime_type: str,
) -> str:
    hasher = hashlib.sha256()
    hasher.update(node_id.encode("utf-8", errors="ignore"))
    hasher.update(filename.encode("utf-8", errors="ignore"))
    hasher.update(mime_type.encode("utf-8", errors="ignore"))
    if source_path and source_path.exists():
        stat = source_path.stat()
        hasher.update(str(stat.st_size).encode())
        hasher.update(str(int(stat.st_mtime_ns)).encode())
    elif source_bytes is not None:
        hasher.update(str(len(source_bytes)).encode())
        hasher.update(hashlib.sha256(source_bytes).digest())
    return hasher.hexdigest()[:32]


def _find_soffice() -> str | None:
    for key in ("LIBREOFFICE_PATH", "SOFFICE_PATH"):
        value = os.getenv(key)
        if not value:
            continue
        candidate = Path(value)
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            for name in ("soffice.exe", "soffice", "libreoffice"):
                executable = candidate / name
                if executable.exists():
                    return str(executable)
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def _convert_with_libreoffice(soffice: str, source_path: Path, out_dir: Path, timeout_seconds: int) -> None:
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(source_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"LibreOffice 退出码 {result.returncode}")


def _fallback(path: Path, mime_type: str, filename: str, error: str) -> OfficePreviewResult:
    try:
        extracted = extract_text_from_path(path, content_type=mime_type, filename=filename)
        text = str(extracted.get("text") or "")[:30_000]
    except Exception:
        text = ""
    return OfficePreviewResult(preview_pdf_path=None, cached=False, error=error, fallback_text=text)


def _fallback_pdf(path: Path, preview_pdf: Path, mime_type: str, filename: str, error: str) -> OfficePreviewResult:
    fallback = _fallback(path, mime_type, filename, error)
    source_text = fallback.fallback_text.strip()
    body = source_text or "原文件为空或无法提取可预览文本。请下载原文件查看。"
    try:
        preview_pdf.parent.mkdir(parents=True, exist_ok=True)
        preview_pdf.write_bytes(
            generate_pdf(
                f"{Path(filename).stem or 'Office 文件'} PDF 预览",
                f"{error}\n\n{body}",
            )
        )
    except Exception:
        return fallback
    return OfficePreviewResult(
        preview_pdf_path=preview_pdf,
        cached=False,
        error=error,
        fallback_text=fallback.fallback_text,
    )
