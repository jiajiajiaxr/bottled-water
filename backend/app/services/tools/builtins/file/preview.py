from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.tools.builtins.file.extractors import extract_text_from_path


def preview_payload(path: Path, *, content_type: str = "", filename: str = "") -> dict[str, Any]:
    extracted = extract_text_from_path(path, content_type=content_type, filename=filename)
    suffix = (path.suffix or Path(filename).suffix).lower()
    mode = "text"
    if suffix == ".pdf" or content_type == "application/pdf":
        mode = "pdf"
    elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
        mode = "image"
    elif suffix in {".docx", ".xlsx", ".pptx"}:
        mode = "office_text"
    return {
        "filename": filename or path.name,
        "content_type": content_type or "application/octet-stream",
        "mode": mode,
        "preview_text": extracted["text"][:30_000],
        "metadata": extracted["metadata"],
    }
