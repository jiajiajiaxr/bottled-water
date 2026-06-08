from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.services.document_model.markdown import markdown_to_sections, parse_markdown_blocks
from app.services.document_model.templates import DOCUMENT_TEMPLATES as TEMPLATE_REGISTRY
from app.services.document_model.templates import get_template, normalize_template_name


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
}
SHORT_PROMPT_MARKERS = (
    "请",
    "帮我",
    "生成",
    "整理",
    "写",
    "制作",
    "起草",
    "输出",
    "做",
    "方案",
    "需求",
    "报告",
    "纪要",
    "实验",
    "总结",
    "分析",
    "计划",
    "部署",
    "发布",
    "交付",
    "验收",
)
TEMPLATE_INFER_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("proposal", ("方案", "部署", "实施", "交付", "发布", "计划", "架构", "项目")),
    ("prd", ("需求", "产品", "功能", "用户", "交互", "流程", "原型")),
    ("meeting", ("会议", "纪要", "议题", "讨论", "例会")),
    ("lab_report", ("实验", "测试", "验证", "数据", "分析")),
    ("report", ("报告", "总结", "分析", "复盘", "汇报", "说明")),
)


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
    explicit_template = bool(value.get("template") or template)
    requested_template = normalize_template_name(value.get("template") or template)
    model_template = _resolve_template_name(
        requested_template,
        model_title,
        model_source,
        explicit_template=explicit_template,
    )
    template_def = get_template(model_template)
    sections = _normalize_sections(value)
    if not sections and _looks_like_short_prompt(model_source):
        sections = _expand_source_sections(
            model_template,
            template_def,
            model_title,
            model_source,
            explicit_template=explicit_template,
        )
    if not sections and model_source:
        sections = markdown_to_sections(model_source)
    if not sections:
        sections = _expand_source_sections(
            model_template,
            template_def,
            model_title,
            model_source,
            explicit_template=explicit_template,
        )
    sections = _merge_source_into_template_sections(sections, model_source)
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
    explicit_template = template is not None
    requested_template = normalize_template_name(template)
    model_template = _resolve_template_name(
        requested_template,
        title,
        source_text,
        explicit_template=explicit_template,
    )
    template_def = get_template(model_template)
    sections = markdown_to_sections(source_text) if source_text else template_def.default_sections()
    if _looks_like_short_prompt(source_text):
        sections = _expand_source_sections(
            model_template,
            template_def,
            title or source_text,
            source_text,
            explicit_template=explicit_template,
        )
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


def _expand_source_sections(
    template_name: str,
    template_def,
    title: str,
    source_text: str,
    *,
    explicit_template: bool,
) -> list[dict[str, Any]]:
    prompt = _clean_text(source_text or title)
    if not prompt:
        return template_def.default_sections()
    if not explicit_template and not _looks_like_document_prompt(title, source_text):
        return _merge_source_into_template_sections(template_def.default_sections(), prompt)
    resolved_template = template_name if explicit_template else _infer_template_name(title, source_text, template_name)
    builder = _PROMPT_SECTION_BUILDERS.get(resolved_template, _report_prompt_sections)
    return builder(prompt)


def _resolve_template_name(
    requested_template: str,
    title: str,
    source_text: str,
    *,
    explicit_template: bool,
) -> str:
    if explicit_template:
        return requested_template
    if _looks_like_document_prompt(title, source_text):
        return _infer_template_name(title, source_text, requested_template)
    return requested_template


def _merge_source_into_template_sections(sections: list[dict[str, Any]], source_text: str) -> list[dict[str, Any]]:
    if not source_text.strip() or not _looks_like_short_prompt(source_text):
        return sections
    merged = deepcopy(sections)
    if merged:
        merged[0].setdefault("blocks", [])
        merged[0]["blocks"].insert(0, {"type": "callout", "title": "用户需求", "text": source_text.strip(), "variant": "info"})
    return merged


def _looks_like_short_prompt(source_text: str) -> bool:
    stripped = source_text.strip()
    if not stripped:
        return False
    return len(stripped) <= 80 and "\n" not in stripped and not stripped.startswith("#")


def _looks_like_document_prompt(title: str, source_text: str) -> bool:
    text = f"{title} {source_text}".strip()
    if not text or "\n" in text:
        return False
    return any(marker in text for marker in SHORT_PROMPT_MARKERS)


def _infer_template_name(title: str, source_text: str, default: str) -> str:
    text = f"{title} {source_text}".strip()
    scores: dict[str, int] = {name: 0 for name in DOCUMENT_TEMPLATES}
    for template_name, keywords in TEMPLATE_INFER_KEYWORDS:
        scores[template_name] += sum(1 for keyword in keywords if keyword in text)
    best = max(scores, key=scores.get)
    return best if scores[best] else default


def _prompt_section(title: str, *blocks: dict[str, Any], level: int = 1) -> dict[str, Any]:
    return {
        "title": _clean_text(title),
        "level": _level(level, default=1),
        "blocks": [block for block in blocks if isinstance(block, dict)],
    }


def _paragraph_block(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "text": _clean_text(text)}


def _list_block(*items: str, ordered: bool = False) -> dict[str, Any]:
    return {
        "type": "list",
        "ordered": ordered,
        "items": [_clean_text(item) for item in items if _clean_text(item)],
    }


def _table_block(headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
    return {
        "type": "table",
        "headers": [_clean_text(item) for item in headers],
        "rows": [[_clean_text(cell) for cell in row] for row in rows],
    }


def _callout_block(title: str, text: str, variant: str = "info") -> dict[str, Any]:
    return {
        "type": "callout",
        "title": _clean_text(title) or "提示",
        "text": _clean_text(text),
        "variant": variant,
    }


def _proposal_prompt_sections(prompt: str) -> list[dict[str, Any]]:
    return [
        _prompt_section(
            "项目背景",
            _callout_block(
                "自动展开说明",
                f'系统已将“{prompt}”整理为项目方案草案，覆盖实施范围、里程碑、风险与验收。',
                "info",
            ),
            _paragraph_block(
                f'本方案围绕“{prompt}”展开，用于快速形成可评审、可交付、可继续细化的结构化文档。'
            ),
        ),
        _prompt_section(
            "目标与范围",
            _paragraph_block("以下内容为通用实施边界，真实项目可继续补充组织信息、接口约束和权限边界。"),
            _list_block("明确本期建设目标", "界定交付范围与边界", "对齐角色、资源和时间安排"),
            _table_block(
                ["阶段", "关键任务", "交付物", "说明"],
                [
                    ["需求确认", "梳理目标、角色和边界", "需求确认纪要", "确认后冻结初版范围"],
                    ["方案设计", "梳理流程、接口和页面结构", "方案文档", "便于评审与拆分任务"],
                    ["迭代开发", "完成实现、联调和缺陷修复", "可运行平台", "支持演示和持续验证"],
                    ["验收交付", "整理说明、发布和交接", "验收材料", "便于归档和移交"],
                ],
            ),
        ),
        _prompt_section(
            "实施计划",
            _table_block(
                ["里程碑", "检查点", "输出"],
                [
                    ["M1 方案确认", "范围和口径对齐", "评审通过的方案草案"],
                    ["M2 联调完成", "核心流程可闭环", "可运行平台与测试记录"],
                    ["M3 验收交付", "资料齐套并完成确认", "验收材料与交付清单"],
                ],
            ),
        ),
        _prompt_section(
            "风险与保障",
            _callout_block(
                "重点风险",
                "重点关注需求变更、环境依赖、数据准备和验收口径四类风险，并提前预留回滚与补齐方案。",
                "warning",
            ),
            _list_block("建立版本管理与评审节奏", "关键节点保留演示样机", "交付前完成清单复核"),
        ),
        _prompt_section(
            "验收标准",
            _list_block(
                "文档、页面和数据流可复核",
                "预览与导出文件可正常打开",
                "各阶段成果可追踪、可回溯",
                ordered=True,
            ),
        ),
    ]


def _report_prompt_sections(prompt: str) -> list[dict[str, Any]]:
    return [
        _prompt_section(
            "摘要",
            _callout_block("自动展开说明", f'系统已将“{prompt}”整理为分析报告草案。', "info"),
            _paragraph_block("本文概括背景、关键观察、主要风险和建议动作，适合用于汇报和复盘。"),
        ),
        _prompt_section(
            "背景与目标",
            _paragraph_block(f'围绕“{prompt}”建立分析脉络，说明业务背景、核心目标和需要重点确认的边界条件。'),
            _list_block("明确问题背景", "对齐分析范围", "约定输出口径"),
        ),
        _prompt_section(
            "分析内容",
            _table_block(
                ["维度", "观察", "影响"],
                [
                    ["现状", "已经形成可阅读的结构化文档", "便于继续补充细节"],
                    ["风险", "仍需补齐真实业务参数与边界", "影响落地精度"],
                    ["动作", "建议在评审中持续确认口径", "降低返工概率"],
                ],
            ),
        ),
        _prompt_section(
            "结论与建议",
            _list_block(
                "形成可执行结论并保留版本记录",
                "明确下一步负责人、时间点和依赖项",
                "在最终交付前完成一次结构复核",
                ordered=True,
            ),
        ),
    ]


def _prd_prompt_sections(prompt: str) -> list[dict[str, Any]]:
    return [
        _prompt_section(
            "产品背景",
            _callout_block("自动展开说明", f'系统已将“{prompt}”整理为需求文档草案。', "info"),
            _paragraph_block("本文围绕目标用户、业务场景、功能边界和验收口径展开。"),
        ),
        _prompt_section(
            "用户场景",
            _list_block("核心用户是谁", "用户要完成什么任务", "成功标准是什么"),
            _paragraph_block("下面的内容适合在产品评审时继续补齐角色、触发条件和异常路径。"),
        ),
        _prompt_section(
            "功能需求",
            _table_block(
                ["模块", "需求描述", "优先级"],
                [
                    ["核心流程", "覆盖主链路操作与结果回传", "P0"],
                    ["辅助能力", "提升协同与可视化效率", "P1"],
                    ["管理配置", "支持参数与权限的基础配置", "P1"],
                ],
            ),
        ),
        _prompt_section(
            "非功能需求",
            _list_block("性能", "安全", "可用性", "可观测性"),
        ),
        _prompt_section(
            "验收指标",
            _paragraph_block("列出可验证的验收条件、测试数据和边界场景，确保需求在实现前就能被明确验证。"),
        ),
    ]


def _meeting_prompt_sections(prompt: str) -> list[dict[str, Any]]:
    return [
        _prompt_section(
            "会议信息",
            _table_block(
                ["项目", "内容"],
                [["主题", prompt], ["参会人", "待确认"], ["主持人", "待确认"], ["记录人", "待确认"]],
            ),
        ),
        _prompt_section(
            "议题与讨论",
            _paragraph_block("按议题记录主要观点、分歧和达成共识，方便会后追踪。"),
            _list_block("议题一：范围确认", "议题二：时间安排", "议题三：风险与依赖"),
        ),
        _prompt_section("会议结论", _list_block("结论一", "结论二", ordered=True)),
        _prompt_section(
            "行动项",
            _table_block(
                ["事项", "负责人", "截止时间", "状态"],
                [["待办事项", "待定", "待定", "未开始"], ["确认资料", "待定", "待定", "未开始"]],
            ),
        ),
        _prompt_section("签字确认", {"type": "signatures", "items": ["主持人", "记录人"]}),
    ]


def _lab_report_prompt_sections(prompt: str) -> list[dict[str, Any]]:
    return [
        _prompt_section(
            "实验目的",
            _paragraph_block(f'围绕“{prompt}”说明需要验证的问题、假设和评价指标。'),
        ),
        _prompt_section(
            "环境与材料",
            _table_block(
                ["类别", "配置"],
                [["软件环境", "待补充"], ["数据/样本", "待补充"], ["工具", "AgentHub"]],
            ),
        ),
        _prompt_section(
            "实验步骤",
            _list_block("准备环境", "执行实验", "记录数据", "复核结果", ordered=True),
        ),
        _prompt_section(
            "结果数据",
            _table_block(
                ["指标", "结果", "说明"],
                [["准确率 / 通过率", "待补充", "待分析"], ["耗时", "待补充", "待分析"]],
            ),
        ),
        _prompt_section(
            "分析讨论",
            _paragraph_block("分析结果是否支持实验假设，说明异常、误差来源和改进方向。"),
        ),
        _prompt_section(
            "结论",
            _callout_block("实验结论", "总结实验发现、适用范围和后续工作。", "success"),
        ),
        _prompt_section("附录", _paragraph_block("补充原始日志、配置、脚本或额外图表。")),
    ]


def _generic_prompt_sections(prompt: str) -> list[dict[str, Any]]:
    return [
        _prompt_section(
            "文档概览",
            _callout_block("自动展开说明", f'系统已将“{prompt}”整理为结构化草案。', "info"),
            _paragraph_block("如需更精确的交付内容，可继续补充背景、约束和验收标准。"),
        ),
        _prompt_section("主要内容", _paragraph_block(f'本文围绕“{prompt}”给出可阅读、可预览、可导出的初稿。')),
    ]


_PROMPT_SECTION_BUILDERS = {
    "proposal": _proposal_prompt_sections,
    "report": _report_prompt_sections,
    "prd": _prd_prompt_sections,
    "meeting": _meeting_prompt_sections,
    "lab_report": _lab_report_prompt_sections,
}


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
