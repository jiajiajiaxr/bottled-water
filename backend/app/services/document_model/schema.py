from __future__ import annotations

import re
from typing import Any


DOCUMENT_TEMPLATES = {"proposal", "report", "prd", "meeting"}
BLOCK_TYPES = {"paragraph", "heading", "list", "table", "callout", "page_break"}


def normalize_document_model(
    value: Any,
    *,
    title: str,
    source_text: str = "",
    template: str | None = None,
) -> dict[str, Any]:
    """把模型参数或 Markdown fallback 统一成可渲染 DocumentModel。"""

    if isinstance(value, dict) and value:
        return _from_mapping(value, title=title, source_text=source_text, template=template)
    return _from_source_text(title=title, source_text=source_text, template=template)


def _from_mapping(
    value: dict[str, Any],
    *,
    title: str,
    source_text: str,
    template: str | None,
) -> dict[str, Any]:
    model_title = str(value.get("title") or title or "AgentHub Document")
    model_template = _template(str(value.get("template") or template or "report"))
    sections = _normalize_sections(value)
    if not sections:
        sections = _from_source_text(
            title=model_title,
            source_text=str(value.get("source_text") or source_text or model_title),
            template=model_template,
        )["sections"]
    return _document(
        title=model_title,
        subtitle=str(value.get("subtitle") or ""),
        sections=sections,
        source_text=str(value.get("source_text") or source_text or ""),
        template=model_template,
    )


def _normalize_sections(value: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sections = value.get("sections")
    if isinstance(raw_sections, list):
        sections = [_section(item) for item in raw_sections if isinstance(item, dict)]
        return [item for item in sections if item["blocks"] or item["title"]]
    blocks = value.get("blocks")
    if isinstance(blocks, list):
        normalized = [_block(item) for item in blocks if isinstance(item, dict)]
        return [{"title": "", "blocks": [item for item in normalized if item]}]
    return []


def _section(value: dict[str, Any]) -> dict[str, Any]:
    blocks = value.get("blocks") if isinstance(value.get("blocks"), list) else []
    return {
        "title": str(value.get("title") or ""),
        "level": _level(value.get("level"), default=1),
        "blocks": [block for item in blocks if isinstance(item, dict) if (block := _block(item))],
    }


def _block(value: dict[str, Any]) -> dict[str, Any]:
    block_type = str(value.get("type") or "paragraph").lower()
    block_type = "page_break" if block_type in {"pagebreak", "break"} else block_type
    if block_type not in BLOCK_TYPES:
        block_type = "paragraph"
    if block_type == "heading":
        return {"type": "heading", "level": _level(value.get("level"), default=2), "text": _text(value)}
    if block_type == "list":
        items = value.get("items") if isinstance(value.get("items"), list) else []
        return {"type": "list", "ordered": bool(value.get("ordered")), "items": [str(item) for item in items]}
    if block_type == "table":
        return _table(value)
    if block_type == "callout":
        return {
            "type": "callout",
            "title": str(value.get("title") or "提示"),
            "text": _text(value),
            "variant": str(value.get("variant") or "info"),
        }
    if block_type == "page_break":
        return {"type": "page_break"}
    return {"type": "paragraph", "text": _text(value)}


def _table(value: dict[str, Any]) -> dict[str, Any]:
    headers = value.get("headers") if isinstance(value.get("headers"), list) else []
    rows = value.get("rows") if isinstance(value.get("rows"), list) else []
    normalized_rows = []
    for row in rows[:80]:
        if isinstance(row, list):
            normalized_rows.append([str(cell) for cell in row[:10]])
        elif isinstance(row, dict):
            normalized_rows.append([str(row.get(header, "")) for header in headers])
    return {"type": "table", "headers": [str(item) for item in headers[:10]], "rows": normalized_rows}


def _from_source_text(title: str, source_text: str, template: str | None) -> dict[str, Any]:
    blocks = _parse_markdown_blocks(source_text or title)
    return _document(
        title=title or "AgentHub Document",
        subtitle="",
        sections=[{"title": "", "level": 1, "blocks": blocks}],
        source_text=source_text,
        template=_template(template or "report"),
    )


def _parse_markdown_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line in {"---", "[pagebreak]", "[page_break]"}:
            blocks.append({"type": "page_break"})
        elif match := re.match(r"^(#{1,4})\s+(.+)$", line):
            blocks.append({"type": "heading", "level": len(match.group(1)), "text": match.group(2)})
        elif line.startswith(">"):
            blocks.append({"type": "callout", "title": "提示", "text": line.lstrip("> ").strip()})
        elif _is_table_line(line):
            table, index = _consume_table(lines, index)
            blocks.append(table)
            continue
        elif re.match(r"^([-*+]|\d+[.)])\s+", line):
            items, ordered, index = _consume_list(lines, index)
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue
        else:
            blocks.append({"type": "paragraph", "text": line})
        index += 1
    return blocks or [{"type": "paragraph", "text": "暂无正文内容。"}]


def _consume_list(lines: list[str], start: int) -> tuple[list[str], bool, int]:
    items: list[str] = []
    ordered = False
    index = start
    while index < len(lines):
        match = re.match(r"^([-*+]|\d+[.)])\s+(.+)$", lines[index].strip())
        if not match:
            break
        ordered = ordered or bool(re.match(r"^\d+", match.group(1)))
        items.append(match.group(2).strip())
        index += 1
    return items, ordered, index


def _consume_table(lines: list[str], start: int) -> tuple[dict[str, Any], int]:
    rows: list[list[str]] = []
    index = start
    while index < len(lines) and _is_table_line(lines[index].strip()):
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        if not all(re.fullmatch(r":?-{2,}:?", cell or "") for cell in cells):
            rows.append(cells)
        index += 1
    headers = rows[0] if rows else []
    return {"type": "table", "headers": headers, "rows": rows[1:]}, index


def _is_table_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 2


def _document(
    *,
    title: str,
    subtitle: str,
    sections: list[dict[str, Any]],
    source_text: str,
    template: str,
) -> dict[str, Any]:
    blocks = [block for section in sections for block in section.get("blocks", [])]
    return {
        "kind": "document",
        "title": title,
        "subtitle": subtitle,
        "template": template,
        "sections": sections,
        "blocks": blocks,
        "source_text": source_text,
    }


def _text(value: dict[str, Any]) -> str:
    return str(value.get("text") or value.get("content") or "")


def _level(value: Any, *, default: int) -> int:
    try:
        return min(max(int(value), 1), 4)
    except (TypeError, ValueError):
        return default


def _template(value: str) -> str:
    return value if value in DOCUMENT_TEMPLATES else "report"
