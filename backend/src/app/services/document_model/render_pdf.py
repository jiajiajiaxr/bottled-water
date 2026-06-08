from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.errors import ValidationAppError


FONT_CANDIDATES = (
    "C:/Windows/Fonts/NotoSansSC-VF.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)


def render_pdf(model: dict[str, Any]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            HRFlowable,
            ListFlowable,
            ListItem,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:  # pragma: no cover
        raise ValidationAppError("reportlab is required to generate PDF artifacts") from exc

    font_name = _register_cjk_font(pdfmetrics, TTFont)
    styles = _styles(getSampleStyleSheet(), ParagraphStyle, colors, font_name, TA_CENTER, TA_LEFT)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=str(model.get("title") or "AgentHub Document"),
    )
    story = _story(model, document.width, styles, Paragraph, Spacer, PageBreak, ListFlowable, ListItem, Table, TableStyle, HRFlowable, colors)
    document.build(story, onFirstPage=_page_footer(model, font_name), onLaterPages=_page_footer(model, font_name))
    return buffer.getvalue()


def _styles(sample, style_factory, colors, font_name: str, align_center, align_left) -> dict[str, Any]:
    base = style_factory(
        "AgentHubBase",
        parent=sample["Normal"],
        fontName=font_name,
        fontSize=10.5,
        leading=17,
        alignment=align_left,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=7,
        wordWrap="CJK",
    )
    return {
        "base": base,
        "cover_kicker": style_factory(
            "AgentHubCoverKicker",
            parent=base,
            fontSize=9,
            leading=13,
            alignment=align_center,
            textColor=colors.HexColor("#2563eb"),
            spaceAfter=10,
        ),
        "title": style_factory(
            "AgentHubTitle",
            parent=base,
            fontSize=29,
            leading=36,
            alignment=align_center,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=16,
        ),
        "subtitle": style_factory(
            "AgentHubSubtitle",
            parent=base,
            fontSize=13,
            leading=20,
            alignment=align_center,
            textColor=colors.HexColor("#475569"),
        ),
        "cover_meta": style_factory(
            "AgentHubCoverMeta",
            parent=base,
            fontSize=10,
            leading=16,
            alignment=align_center,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=5,
        ),
        "h1": style_factory(
            "AgentHubH1",
            parent=base,
            fontSize=19,
            leading=25,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor("#0f172a"),
        ),
        "h2": style_factory(
            "AgentHubH2",
            parent=base,
            fontSize=15,
            leading=21,
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.HexColor("#1e3a8a"),
        ),
        "h3": style_factory(
            "AgentHubH3",
            parent=base,
            fontSize=12.5,
            leading=18,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor("#334155"),
        ),
        "toc_item": style_factory(
            "AgentHubTocItem",
            parent=base,
            fontSize=11,
            leading=18,
            textColor=colors.HexColor("#334155"),
        ),
        "table": style_factory(
            "AgentHubTable",
            parent=base,
            fontSize=9.2,
            leading=14,
            spaceAfter=0,
        ),
        "table_header": style_factory(
            "AgentHubTableHeader",
            parent=base,
            fontSize=9.4,
            leading=14,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=0,
        ),
        "quote": style_factory(
            "AgentHubQuote",
            parent=base,
            leftIndent=10,
            textColor=colors.HexColor("#475569"),
        ),
        "small": style_factory(
            "AgentHubSmall",
            parent=base,
            fontSize=8.5,
            leading=13,
            textColor=colors.HexColor("#64748b"),
        ),
    }


def _story(
    model: dict[str, Any],
    available_width: float,
    styles: dict[str, Any],
    paragraph,
    spacer,
    page_break,
    list_flowable,
    list_item,
    table,
    table_style,
    hr_flowable,
    colors,
) -> list[Any]:
    story = _cover(model, styles, paragraph, spacer, page_break, hr_flowable, colors)
    if (model.get("toc") or {}).get("enabled", True):
        story.extend(_toc(model, styles, paragraph, page_break))
    for section in model.get("sections", []):
        story.extend(_section_flowables(section, available_width, styles, paragraph, page_break, list_flowable, list_item, table, table_style, hr_flowable, colors))
    if model.get("appendix"):
        story.extend([page_break(), paragraph("附录", styles["h1"])])
        for section in model["appendix"]:
            story.extend(_section_flowables(section, available_width, styles, paragraph, page_break, list_flowable, list_item, table, table_style, hr_flowable, colors))
    if model.get("signatures"):
        story.extend(_signature_flowables(model["signatures"], available_width, paragraph, styles, table, table_style, colors))
    return story


def _cover(model: dict[str, Any], styles, paragraph, spacer, page_break, hr_flowable, colors) -> list[Any]:
    cover = model.get("cover") or {}
    story = [
        spacer(1, 46),
        paragraph("AGENTHUB DOCUMENT", styles["cover_kicker"]),
        paragraph(_escape(str(cover.get("title") or model.get("title") or "AgentHub 文档")), styles["title"]),
    ]
    subtitle = str(cover.get("subtitle") or model.get("subtitle") or "")
    if subtitle:
        story.append(paragraph(_escape(subtitle), styles["subtitle"]))
    story.extend(
        [
            spacer(1, 18),
            hr_flowable(
                width="42%",
                thickness=1.2,
                color=colors.HexColor("#2563eb"),
                hAlign="CENTER",
                spaceBefore=8,
                spaceAfter=18,
            ),
        ]
    )
    meta = [
        str(cover.get("issuer") or "AgentHub"),
        str(cover.get("confidentiality") or ""),
        f"{cover.get('date_label') or '生成日期'}：{cover.get('date') or ''}",
    ]
    story.extend(paragraph(_escape(item), styles["cover_meta"]) for item in meta if item)
    story.extend(
        [
            spacer(1, 120),
            paragraph("结构化生成 · 可预览 · 可导出 · 可归档", styles["small"]),
            page_break(),
        ]
    )
    return story


def _toc(model: dict[str, Any], styles, paragraph, page_break) -> list[Any]:
    title = str((model.get("toc") or {}).get("title") or "目录")
    flowables = [paragraph(_escape(title), styles["h1"])]
    section_titles = [str(item.get("title") or "") for item in model.get("sections", []) if item.get("title")]
    for index, section_title in enumerate(section_titles, start=1):
        flowables.append(paragraph(_escape(f"{index:02d}  {section_title}"), styles["toc_item"]))
    return [*flowables, page_break()]


def _section_flowables(section: dict[str, Any], available_width: float, styles, paragraph, page_break, list_flowable, list_item, table, table_style, hr_flowable, colors) -> list[Any]:
    flowables: list[Any] = []
    if section.get("title"):
        flowables.append(paragraph(_escape(str(section["title"])), styles["h1"]))
        flowables.append(
            hr_flowable(
                width="100%",
                thickness=0.8,
                color=colors.HexColor("#dbeafe"),
                spaceBefore=0,
                spaceAfter=6,
            )
        )
    for block in section.get("blocks", []):
        flowables.extend(_block_flowables(block, available_width, styles, paragraph, page_break, list_flowable, list_item, table, table_style, hr_flowable, colors))
    return flowables


def _block_flowables(block: dict[str, Any], available_width: float, styles, paragraph, page_break, list_flowable, list_item, table, table_style, hr_flowable, colors) -> list[Any]:
    block_type = block.get("type")
    if block_type == "heading":
        level = min(max(int(block.get("level") or 2), 1), 3)
        return [paragraph(_escape(str(block.get("text") or "")), styles[f"h{level}"])]
    if block_type == "list":
        items = [list_item(paragraph(_escape(str(item)), styles["base"])) for item in block.get("items", [])]
        bullet_type = "1" if block.get("ordered") else "bullet"
        return [list_flowable(items, bulletType=bullet_type, leftIndent=18)] if items else []
    if block_type == "table":
        return _table_flowable(block, available_width, paragraph, styles, table, table_style, colors)
    if block_type == "callout":
        title = _escape(str(block.get("title") or "提示"))
        text = _escape(str(block.get("text") or ""))
        cell = paragraph(f"<b>{title}：</b>{text}", styles["base"])
        return _boxed_flowable(
            cell,
            available_width,
            table,
            table_style,
            colors,
            str(block.get("variant") or "info"),
        )
    if block_type == "quote":
        return [paragraph(f"“{_escape(str(block.get('text') or ''))}”", styles["quote"])]
    if block_type == "image":
        alt = _escape(str(block.get("alt") or block.get("src") or "未命名图片"))
        return [paragraph(f"[图片占位：{alt}]", styles["small"])]
    if block_type == "divider":
        return [hr_flowable(width="100%", thickness=0.6, color=colors.HexColor("#cbd5e1"), spaceBefore=8, spaceAfter=8)]
    if block_type == "page_break":
        return [page_break()]
    if block_type == "signatures":
        return _signature_flowables(block.get("items") or [], available_width, paragraph, styles, table, table_style, colors)
    text = str(block.get("text") or "")
    return [paragraph(_escape(text), styles["base"])] if text.strip() else []


def _table_flowable(block: dict[str, Any], available_width: float, paragraph, styles, table, table_style, colors) -> list[Any]:
    headers = [str(item) for item in block.get("headers", [])]
    rows = [[str(cell) for cell in row] for row in block.get("rows", [])]
    if not headers and not rows:
        return []
    data = [headers] if headers else []
    data.extend(rows)
    column_count = max(len(row) for row in data)
    col_widths = [available_width / column_count] * column_count
    table_data = []
    for row_index, row in enumerate(data):
        style = styles["table_header"] if headers and row_index == 0 else styles["table"]
        table_data.append(
            [paragraph(_escape(cell), style) for cell in row + [""] * (column_count - len(row))]
        )
    flowable = table(table_data, colWidths=col_widths, hAlign="LEFT", repeatRows=1 if headers else 0)
    style_commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    if headers:
        style_commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                ("LINEBELOW", (0, 0), (-1, 0), 1.0, colors.HexColor("#38bdf8")),
            ]
        )
    for row_index in range(1 if headers else 0, len(table_data)):
        if row_index % 2 == 0:
            style_commands.append(
                ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#f8fafc"))
            )
    flowable.setStyle(table_style(style_commands))
    return [flowable]


def _boxed_flowable(cell, available_width: float, table, table_style, colors, variant: str) -> list[Any]:
    background, border = _callout_palette(variant)
    flowable = table([[cell]], colWidths=[available_width], hAlign="LEFT")
    flowable.setStyle(
        table_style(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(border)),
                ("LINEBEFORE", (0, 0), (0, -1), 2.0, colors.HexColor(border)),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return [flowable]


def _callout_palette(variant: str) -> tuple[str, str]:
    return {
        "warning": ("#fff7ed", "#f59e0b"),
        "success": ("#f0fdf4", "#22c55e"),
        "danger": ("#fef2f2", "#ef4444"),
        "error": ("#fef2f2", "#ef4444"),
    }.get(variant, ("#eff6ff", "#3b82f6"))


def _signature_flowables(items: list[str], available_width: float, paragraph, styles, table, table_style, colors) -> list[Any]:
    names = [str(item) for item in items if str(item).strip()] or ["负责人", "确认人"]
    data = [["角色", "签字", "日期"], *[[name, "", ""] for name in names]]
    flowable = table([[paragraph(_escape(cell), styles["base"]) for cell in row] for row in data], colWidths=[available_width * 0.25, available_width * 0.45, available_width * 0.3])
    flowable.setStyle(
        table_style(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return [paragraph("签字确认", styles["h1"]), flowable]


def _page_footer(model: dict[str, Any], font_name: str):
    title = str(model.get("title") or "AgentHub")
    header = str((model.get("template_spec") or {}).get("header") or "AgentHub 文档")

    def draw(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(font_name, 8.5)
        canvas.setFillColorRGB(0.45, 0.5, 0.56)
        canvas.drawString(document.leftMargin, document.pagesize[1] - 13, f"{header} · {title}")
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 15, f"第 {document.page} 页")
        canvas.restoreState()

    return draw


def _register_cjk_font(pdfmetrics, ttfont_factory) -> str:
    font_name = "AgentHubCJK"
    if font_name in pdfmetrics.getRegisteredFontNames():
        return font_name
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            pdfmetrics.registerFont(ttfont_factory(font_name, str(path)))
            return font_name
        except Exception:
            continue
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    fallback = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(fallback))
    return fallback


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
