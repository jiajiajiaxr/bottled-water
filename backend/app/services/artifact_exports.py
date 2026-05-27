from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from app.models import Artifact
from app.services.artifact_storage import BINARY_ARTIFACT_FORMATS
from app.services.file_tools import generate_pdf
from app.services.serialization import artifact_to_dict


@dataclass(frozen=True)
class ArtifactExport:
    content: bytes
    media_type: str
    filename: str


OFFICE_MIME_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
}

DOWNLOAD_FORMAT_ALIASES = {
    "web_app": "html",
    "htm": "html",
    "markdown": "md",
}

DOWNLOAD_FORMATS = {"pdf", "docx", "xlsx", "pptx", "html", "md", "json", "zip"}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "div", "section", "article", "header", "footer", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        value = " ".join(self.parts)
        value = re.sub(r"\s*\n\s*", "\n", value)
        value = re.sub(r"[ \t]{2,}", " ", value)
        return value.strip()


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return (cleaned or fallback)[:80]


def _files(artifact: Artifact) -> dict[str, str]:
    content = artifact.content or {}
    files = content.get("files") if isinstance(content.get("files"), dict) else {}
    normalized = {str(path): str(value) for path, value in files.items()}
    if not normalized:
        html = content.get("preview_html") or content.get("html") or ""
        normalized["index.html"] = str(html)
    return normalized


def _primary_text(artifact: Artifact) -> str:
    files = _files(artifact)
    html = files.get("index.html") or next(iter(files.values()), "")
    extractor = TextExtractor()
    extractor.feed(html)
    text = extractor.text()
    return text or artifact.description or artifact.name


def _markdown(artifact: Artifact) -> str:
    text = _primary_text(artifact)
    lines = [f"# {artifact.name}", "", artifact.description.strip(), "", "## Content", "", text]
    if artifact.type == "spreadsheet":
        lines.extend(["", "## Table Export", "", "| Item | Value |", "| --- | --- |", "| Status | Ready |"])
    if artifact.type == "slides":
        lines.extend(["", "## Slides", "", "- Title slide", "- Solution overview", "- Review result"])
    return "\n".join(line for line in lines if line is not None)


def _zip_bytes(files: dict[str, str], metadata: dict[str, Any], binary_files: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        archive.writestr("README.md", metadata.get("readme", "AgentHub artifact export"))
        for path, content in (binary_files or {}).items():
            archive.writestr(path, content)
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def _docx_bytes(title: str, body: str) -> bytes:
    body_xml = "".join(f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in body.splitlines() if line.strip())
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        f"<w:p><w:r><w:t>{escape(title)}</w:t></w:r></w:p>"
        f"{body_xml}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _xlsx_bytes(title: str, body: str) -> bytes:
    rows = [[title], *[[line] for line in body.splitlines() if line.strip()][:80]]
    sheet_rows = []
    for index, row in enumerate(rows, start=1):
        cells = "".join(f'<c r="{chr(64 + col)}{index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>' for col, value in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{index}">{cells}</row>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="AgentHub" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
    return buffer.getvalue()


def _pptx_bytes(title: str, body: str) -> bytes:
    first_lines = [line for line in body.splitlines() if line.strip()][:6]
    slide_text = escape("\n".join(first_lines) or body[:500])
    slide = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
        f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{escape(title)}</a:t></a:r></a:p><a:p><a:r><a:t>{slide_text}</a:t></a:r></a:p></p:txBody></p:sp>'
        "</p:spTree></p:cSld></p:sld>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>')
        archive.writestr("ppt/presentation.xml", '<?xml version="1.0" encoding="UTF-8"?><p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>')
        archive.writestr("ppt/_rels/presentation.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>')
        archive.writestr("ppt/slides/slide1.xml", slide)
    return buffer.getvalue()


def default_export_format(artifact: Artifact) -> str:
    content_format = _normalize_export_format((artifact.content or {}).get("format"))
    if content_format in DOWNLOAD_FORMATS:
        return content_format
    tool_format = ((artifact.content or {}).get("tool_output") or {}).get("format")
    tool_format = _normalize_export_format(tool_format)
    if tool_format in DOWNLOAD_FORMATS:
        return tool_format
    return {
        "document": "docx",
        "spreadsheet": "xlsx",
        "slides": "pptx",
        "code": "zip",
        "web_app": "zip",
    }.get(artifact.type, "zip")


def export_artifact(artifact: Artifact, export_format: str | None = None) -> ArtifactExport:
    fmt = _normalize_export_format(export_format or default_export_format(artifact))
    stored = _stored_artifact_export(artifact, fmt)
    if stored:
        return stored
    files = _files(artifact)
    base = _safe_name(artifact.name, f"artifact-{artifact.id[:8]}")
    metadata = artifact_to_dict(artifact)
    metadata["readme"] = _markdown(artifact)
    primary_html = files.get("index.html") or next(iter(files.values()), "")
    body = _primary_text(artifact)

    if fmt in {"html", "htm"}:
        return ArtifactExport(primary_html.encode("utf-8"), "text/html; charset=utf-8", f"{base}.html")
    if fmt in {"md", "markdown"}:
        return ArtifactExport(_markdown(artifact).encode("utf-8"), "text/markdown; charset=utf-8", f"{base}.md")
    if fmt == "json":
        content = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
        return ArtifactExport(content, "application/json; charset=utf-8", f"{base}.json")
    if fmt == "docx":
        return ArtifactExport(_docx_bytes(artifact.name, body), OFFICE_MIME_TYPES["docx"], f"{base}.docx")
    if fmt == "xlsx":
        return ArtifactExport(_xlsx_bytes(artifact.name, body), OFFICE_MIME_TYPES["xlsx"], f"{base}.xlsx")
    if fmt == "pptx":
        return ArtifactExport(_pptx_bytes(artifact.name, body), OFFICE_MIME_TYPES["pptx"], f"{base}.pptx")
    if fmt == "pdf":
        return ArtifactExport(generate_pdf(artifact.name, body), OFFICE_MIME_TYPES["pdf"], f"{base}.pdf")
    if fmt != "zip":
        raise ValueError(f"unsupported export format: {fmt}")
    content = _artifact_zip_bytes(artifact, files, metadata)
    return ArtifactExport(content, "application/zip", f"{base}.zip")


def _stored_artifact_export(artifact: Artifact, fmt: str) -> ArtifactExport | None:
    content = artifact.content or {}
    if fmt not in BINARY_ARTIFACT_FORMATS and fmt != content.get("format"):
        return None
    descriptor = content.get("export_file") or content.get("source_file")
    if not isinstance(descriptor, dict) or descriptor.get("format") != fmt:
        return None
    path_value = descriptor.get("storage_path")
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.exists() or not path.is_file():
        return None
    media_type = str(descriptor.get("media_type") or OFFICE_MIME_TYPES.get(fmt) or artifact.mime_type)
    filename = str(descriptor.get("filename") or f"{_safe_name(artifact.name, artifact.id[:8])}.{fmt}")
    return ArtifactExport(path.read_bytes(), media_type, filename)


def _artifact_zip_bytes(artifact: Artifact, files: dict[str, str], metadata: dict[str, Any]) -> bytes:
    content = artifact.content or {}
    preview_html = str(content.get("preview_html") or files.get("index.html") or "")
    text_files = {"preview.html": preview_html, **files}
    binary_files = _artifact_binary_files(artifact)
    return _zip_bytes(text_files, metadata, binary_files)


def _artifact_binary_files(artifact: Artifact) -> dict[str, bytes]:
    descriptor = ((artifact.content or {}).get("export_file") or (artifact.content or {}).get("source_file"))
    if not isinstance(descriptor, dict):
        return {}
    path_value = descriptor.get("storage_path")
    if not path_value:
        return {}
    path = Path(str(path_value))
    if not path.exists() or not path.is_file():
        return {}
    filename = str(descriptor.get("filename") or path.name)
    return {f"source/{filename}": path.read_bytes()}


def _normalize_export_format(value: Any) -> str:
    fmt = str(value or "").lower().strip(".")
    return DOWNLOAD_FORMAT_ALIASES.get(fmt, fmt)
