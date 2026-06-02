from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.services.document_model.markdown import markdown_to_sections, parse_markdown_blocks
from app.services.document_model.templates import DOCUMENT_TEMPLATES as TEMPLATE_REGISTRY
from app.services.document_model.templates import get_template, infer_template_name, normalize_template_name


DOCUMENT_TEMPLATES = set(TEMPLATE_REGISTRY)
BLOCK_TYPES = {
    "paragraph",
    "heading",
    "list",
    "table",
    "callout",
    "quote",
    "image",
    "divider",
    "page_break",
    "signatures",
    "risk_item",
    "action_plan",
    "summary",
    "conclusion",
}


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
    model_title = _clean_text(value.get("title") or title or "AgentHub Document")
    model_source = _clean_text(value.get("source_text") or value.get("body") or source_text or "")
    template_hint = value.get("template") or template
    model_template = normalize_template_name(template_hint or infer_template_name(model_title, model_source))
    template_def = get_template(model_template)
    sections = _normalize_sections(value)
    if not sections and model_source:
        sections = markdown_to_sections(model_source)
    if not sections:
        sections = template_def.default_sections()
    sections = _merge_source_into_template_sections(sections, model_source, model_template)
    sections = _ensure_required_sections(sections, model_template)
    return _document(
        title=model_title,
        subtitle=_clean_text(value.get("subtitle") or template_def.subtitle),
        sections=sections,
        source_text=model_source,
        template=model_template,
        cover=_normalize_cover(value.get("cover"), template_def.cover, model_title, value.get("subtitle")),
        toc=_normalize_toc(value.get("toc")),
        metadata=_normalize_metadata(value.get("metadata"), model_template),
        tables=_normalize_named_blocks(value.get("tables"), "table"),
        callouts=_normalize_named_blocks(value.get("callouts"), "callout"),
        signatures=_normalize_signatures(value.get("signatures")),
        appendix=_normalize_appendix(value.get("appendix")),
        template_spec=template_def.to_dict(),
    )


def _from_source_text(title: str, source_text: str, template: str | None) -> dict[str, Any]:
    model_template = normalize_template_name(template or infer_template_name(title, source_text))
    template_def = get_template(model_template)
    sections = markdown_to_sections(source_text) if source_text else template_def.default_sections()
    if _looks_like_short_prompt(source_text):
        sections = _merge_source_into_template_sections(template_def.default_sections(), source_text, model_template)
    sections = _ensure_required_sections(sections, model_template)
    return _document(
        title=title or "AgentHub Document",
        subtitle=template_def.subtitle,
        sections=sections,
        source_text=source_text,
        template=model_template,
        cover=_normalize_cover(None, template_def.cover, title, None),
        toc={"enabled": True, "title": "目录"},
        metadata=_normalize_metadata(None, model_template),
        tables=[],
        callouts=[],
        signatures=[],
        appendix=[],
        template_spec=template_def.to_dict(),
    )


def _normalize_sections(value: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sections = value.get("sections")
    if isinstance(raw_sections, list):
        sections = [_section(item) for item in raw_sections if isinstance(item, dict)]
        return [item for item in sections if item["blocks"] or item["title"]]
    blocks = value.get("blocks")
    if isinstance(blocks, list):
        normalized = [_block(item) for item in blocks if isinstance(item, dict)]
        return [{"title": "", "level": 1, "blocks": [item for item in normalized if item]}]
    return []


def _section(value: dict[str, Any]) -> dict[str, Any]:
    blocks = value.get("blocks") if isinstance(value.get("blocks"), list) else []
    if not blocks and value.get("content"):
        blocks = parse_markdown_blocks(str(value["content"]))
    return {
        "title": _clean_text(value.get("title")),
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
        return {"type": "list", "ordered": bool(value.get("ordered")), "items": [_clean_text(item) for item in items]}
    if block_type == "table":
        return _table(value)
    if block_type == "callout":
        return {
            "type": "callout",
            "title": _clean_text(value.get("title") or "提示"),
            "text": _text(value),
            "variant": _clean_text(value.get("variant") or "info"),
        }
    if block_type == "quote":
        return {"type": "quote", "text": _text(value)}
    if block_type == "image":
        return {"type": "image", "src": _clean_text(value.get("src")), "alt": _clean_text(value.get("alt"))}
    if block_type == "divider":
        return {"type": "divider"}
    if block_type == "page_break":
        return {"type": "page_break"}
    if block_type == "signatures":
        items = value.get("items") if isinstance(value.get("items"), list) else []
        return {"type": "signatures", "items": [_clean_text(item) for item in items]}
    if block_type == "risk_item":
        return {
            "type": "risk_item",
            "items": _normalize_matrix_items(value, headers=("风险", "级别", "影响", "缓解措施")),
        }
    if block_type == "action_plan":
        return {
            "type": "action_plan",
            "items": _normalize_matrix_items(value, headers=("事项", "负责人", "时间", "状态")),
        }
    if block_type == "summary":
        return {"type": "summary", "text": _text(value)}
    if block_type == "conclusion":
        return {"type": "conclusion", "text": _text(value)}
    return {"type": "paragraph", "text": _text(value)}


def _table(value: dict[str, Any]) -> dict[str, Any]:
    headers = value.get("headers") if isinstance(value.get("headers"), list) else []
    rows = value.get("rows") if isinstance(value.get("rows"), list) else []
    normalized_rows = []
    for row in rows[:120]:
        if isinstance(row, list):
            normalized_rows.append([_clean_text(cell) for cell in row[:12]])
        elif isinstance(row, dict):
            normalized_rows.append([_clean_text(row.get(header, "")) for header in headers[:12]])
    return {"type": "table", "headers": [_clean_text(item) for item in headers[:12]], "rows": normalized_rows}


def _normalize_matrix_items(value: dict[str, Any], *, headers: tuple[str, ...]) -> list[list[str]]:
    raw_items = value.get("items") if isinstance(value.get("items"), list) else value.get("rows")
    if not isinstance(raw_items, list):
        raw_items = []
    key_map = {
        "风险": ("risk", "name", "title", "issue"),
        "级别": ("level", "severity", "priority"),
        "影响": ("impact", "effect"),
        "缓解措施": ("mitigation", "action", "measure"),
        "事项": ("task", "item", "name", "title"),
        "负责人": ("owner", "assignee", "responsible"),
        "时间": ("due", "deadline", "time"),
        "状态": ("status", "state"),
    }
    rows: list[list[str]] = []
    for item in raw_items[:60]:
        if isinstance(item, list):
            rows.append([_clean_text(cell) for cell in item[: len(headers)]])
        elif isinstance(item, dict):
            row = []
            for header in headers:
                keys = key_map.get(header, ())
                row.append(next((_clean_text(item.get(key)) for key in keys if _clean_text(item.get(key))), ""))
            rows.append(row)
        elif _clean_text(item):
            rows.append([_clean_text(item), "", "", ""])
    return rows


def _normalize_cover(value: Any, defaults: dict[str, Any], title: str, subtitle: Any) -> dict[str, Any]:
    cover = deepcopy(defaults)
    if isinstance(value, dict):
        cover.update({str(key): _clean_text(item) for key, item in value.items() if item is not None})
    cover.setdefault("issuer", "AgentHub")
    cover["title"] = _clean_text(cover.get("title") or title)
    cover["subtitle"] = _clean_text(cover.get("subtitle") or subtitle or "")
    cover.setdefault("date", datetime.now(UTC).date().isoformat())
    return cover


def _normalize_toc(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"enabled": bool(value.get("enabled", True)), "title": _clean_text(value.get("title") or "目录")}
    return {"enabled": True, "title": "目录"}


def _normalize_metadata(value: Any, template: str) -> dict[str, Any]:
    metadata = {"template": template, "source": "AgentHub", "generated_at": datetime.now(UTC).isoformat()}
    if isinstance(value, dict):
        metadata.update({str(key): _clean_text(item) for key, item in value.items() if item is not None})
    return metadata


def _normalize_named_blocks(value: Any, expected_type: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    blocks = [_block(item) for item in value if isinstance(item, dict)]
    return [block for block in blocks if block.get("type") == expected_type]


def _normalize_signatures(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _normalize_appendix(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [_section(item) for item in value if isinstance(item, dict)]
    if isinstance(value, str) and value.strip():
        return [{"title": "附录", "level": 1, "blocks": parse_markdown_blocks(value)}]
    return []


def _merge_source_into_template_sections(
    sections: list[dict[str, Any]],
    source_text: str,
    template: str,
) -> list[dict[str, Any]]:
    if not source_text.strip() or not _looks_like_short_prompt(source_text):
        return sections
    merged = deepcopy(sections)
    if not merged:
        return merged
    merged[0].setdefault("blocks", [])
    merged[0]["blocks"].insert(
        0,
        {"type": "callout", "title": "用户需求", "text": source_text.strip(), "variant": "info"},
    )
    merged[0]["blocks"].append({"type": "paragraph", "text": _requirement_summary(source_text, template)})
    return merged


def _ensure_required_sections(sections: list[dict[str, Any]], template: str) -> list[dict[str, Any]]:
    merged = deepcopy(sections)
    existing = {str(section.get("title") or "") for section in merged}
    defaults: list[tuple[str, dict[str, Any]]] = [
        ("摘要", {"type": "summary", "text": "概括文档背景、目标、核心内容和最终建议。"}),
        ("风险项", {"type": "risk_item", "items": [["待识别风险", "中", "待评估", "制定缓解措施"]]}),
        ("行动计划", {"type": "action_plan", "items": [["明确下一步行动", "负责人待定", "近期", "待启动"]]}),
        ("结论", {"type": "conclusion", "text": "总结当前判断、适用范围和后续建议。"}),
    ]
    if template == "lab_report":
        defaults.insert(1, ("实验目的", {"type": "paragraph", "text": "说明实验要验证的问题、假设和评价指标。"}))
    for section_title, block in defaults:
        if section_title not in existing:
            merged.append({"title": section_title, "level": 1, "blocks": [block]})
            existing.add(section_title)
    return merged


def _looks_like_short_prompt(source_text: str) -> bool:
    stripped = source_text.strip()
    if not stripped:
        return False
    return len(stripped) <= 100 and "\n" not in stripped and not stripped.startswith("#")


def _requirement_summary(source_text: str, template: str) -> str:
    label = get_template(template).label
    return (
        f"本文件将围绕“{source_text.strip()}”生成{label}，"
        "并补齐摘要、目录、章节、风险项、行动计划和结论，便于直接用于演示或交付。"
    )


def _document(
    *,
    title: str,
    subtitle: str,
    sections: list[dict[str, Any]],
    source_text: str,
    template: str,
    cover: dict[str, Any],
    toc: dict[str, Any],
    metadata: dict[str, Any],
    tables: list[dict[str, Any]],
    callouts: list[dict[str, Any]],
    signatures: list[str],
    appendix: list[dict[str, Any]],
    template_spec: dict[str, Any],
) -> dict[str, Any]:
    blocks = [block for section in [*sections, *appendix] for block in section.get("blocks", [])]
    return {
        "kind": "document",
        "title": title,
        "subtitle": subtitle,
        "template": template,
        "cover": cover,
        "toc": toc,
        "metadata": metadata,
        "sections": sections,
        "blocks": blocks,
        "tables": tables,
        "callouts": callouts,
        "signatures": signatures,
        "appendix": appendix,
        "template_spec": template_spec,
        "source_text": source_text,
    }


def _text(value: dict[str, Any]) -> str:
    return _clean_text(value.get("text") or value.get("content") or "")


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _level(value: Any, *, default: int) -> int:
    try:
        return min(max(int(value), 1), 4)
    except (TypeError, ValueError):
        return default
