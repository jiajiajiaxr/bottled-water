from __future__ import annotations

import re
from typing import Any


def parse_markdown_blocks(text: str) -> list[dict[str, Any]]:
    """把 Markdown 文本解析成稳定的 DocumentModel blocks。"""

    blocks: list[dict[str, Any]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if _is_page_break(line):
            blocks.append({"type": "page_break"})
        elif _is_divider(line):
            blocks.append({"type": "divider"})
        elif image := _image(line):
            blocks.append(image)
        elif match := re.match(r"^(#{1,6})\s+(.+)$", line):
            blocks.append({"type": "heading", "level": min(len(match.group(1)), 4), "text": match.group(2).strip()})
        elif line.startswith(">"):
            block, index = _consume_quote_or_callout(lines, index)
            blocks.append(block)
            continue
        elif _is_table_line(line):
            table, index = _consume_table(lines, index)
            blocks.append(table)
            continue
        elif re.match(r"^([-*+]|\d+[.)])\s+", line):
            items, ordered, index = _consume_list(lines, index)
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue
        else:
            paragraph, index = _consume_paragraph(lines, index)
            blocks.append({"type": "paragraph", "text": paragraph})
            continue
        index += 1
    return blocks or [{"type": "paragraph", "text": "暂无正文内容。"}]


def markdown_to_sections(text: str) -> list[dict[str, Any]]:
    blocks = parse_markdown_blocks(text)
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for block in blocks:
        if block.get("type") == "heading" and int(block.get("level") or 1) <= 2:
            current = {"title": str(block.get("text") or ""), "level": 1, "blocks": []}
            sections.append(current)
            continue
        if current is None:
            current = {"title": "", "level": 1, "blocks": []}
            sections.append(current)
        current["blocks"].append(block)
    return [section for section in sections if section["title"] or section["blocks"]]


def _consume_paragraph(lines: list[str], start: int) -> tuple[str, int]:
    parts: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index].strip()
        if not line or _starts_special_block(line):
            break
        parts.append(line)
        index += 1
    return " ".join(parts).strip(), index


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


def _consume_quote_or_callout(lines: list[str], start: int) -> tuple[dict[str, Any], int]:
    parts: list[str] = []
    index = start
    while index < len(lines) and lines[index].strip().startswith(">"):
        parts.append(lines[index].strip().lstrip("> ").strip())
        index += 1
    title = "提示"
    variant = "info"
    if parts and (match := re.match(r"^\[!(\w+)]\s*(.*)$", parts[0], re.I)):
        variant = match.group(1).lower()
        title = match.group(2).strip() or variant.upper()
        parts = parts[1:]
        return {"type": "callout", "title": title, "variant": variant, "text": "\n".join(parts).strip()}, index
    return {"type": "quote", "text": "\n".join(parts).strip()}, index


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


def _image(line: str) -> dict[str, Any] | None:
    match = re.match(r"^!\[(?P<alt>[^\]]*)]\((?P<src>[^)]+)\)$", line)
    if not match:
        return None
    return {"type": "image", "alt": match.group("alt"), "src": match.group("src")}


def _starts_special_block(line: str) -> bool:
    return (
        _is_page_break(line)
        or _is_divider(line)
        or _is_table_line(line)
        or bool(_image(line))
        or line.startswith(">")
        or bool(re.match(r"^(#{1,6})\s+.+$", line))
        or bool(re.match(r"^([-*+]|\d+[.)])\s+", line))
    )


def _is_table_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 2


def _is_page_break(line: str) -> bool:
    return line.lower() in {"[pagebreak]", "[page_break]", "<!-- pagebreak -->", "<!-- page_break -->"}


def _is_divider(line: str) -> bool:
    return bool(re.fullmatch(r"[-*_]{3,}", line))
