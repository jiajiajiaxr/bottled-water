from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.tools.builtins.file.extractors import extract_text_from_path
from app.services.tools.builtins.file.converters import TEXT_EXTENSIONS, TEXT_TYPES, _decode


def preview_payload(path: Path, *, content_type: str = "", filename: str = "") -> dict[str, Any]:
    extracted = extract_text_from_path(path, content_type=content_type, filename=filename)
    suffix = (path.suffix or Path(filename).suffix).lower()
    mode = "text"
    raw_text = ""
    if content_type in TEXT_TYPES or suffix in TEXT_EXTENSIONS:
        raw_text = _decode(path.read_bytes())[:200_000]
    if suffix == ".pdf" or content_type == "application/pdf":
        mode = "pdf"
    elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
        mode = "image"
    elif suffix in {".html", ".htm"} or "html" in content_type:
        mode = "html"
    elif suffix in {".docx", ".xlsx", ".pptx"}:
        mode = "office_text"
    text = raw_text or extracted["text"][:30_000]
    if not text and mode == "text" and extracted["metadata"].get("extractor") == "unsupported":
        mode = "binary"
    return {
        "filename": filename or path.name,
        "content_type": content_type or "application/octet-stream",
        "mode": mode,
        "text": text,
        "preview_text": text,
        "metadata": extracted["metadata"],
    }
