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
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=str(model.get("title") or "AgentHub Document"),
    )
    story = _story(model, styles, Paragraph, Spacer, PageBreak, ListFlowable, ListItem, Table, TableStyle, colors)
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
    )
    return {
        "base": base,
        "title": style_factory("AgentHubTitle", parent=base, fontSize=27, leading=34, alignment=align_center),
        "subtitle": style_factory("AgentHubSubtitle", parent=base, fontSize=13, leading=20, alignment=align_center),
        "h1": style_factory("AgentHubH1", parent=base, fontSize=20, leading=26, spaceBefore=12),
        "h2": style_factory("AgentHubH2", parent=base, fontSize=15, leading=21, spaceBefore=10),
        "h3": style_factory("AgentHubH3", parent=base, fontSize=12.5, leading=18, spaceBefore=8),
        "callout": style_factory("AgentHubCallout", parent=base, leftIndent=8, rightIndent=8),
    }


def _story(
    model: dict[str, Any],
    styles: dict[str, Any],
    paragraph,
    spacer,
    page_break,
    list_flowable,
    list_item,
    table,
    table_style,
    colors,
) -> list[Any]:
    story: list[Any] = [
        spacer(1, 46),
        paragraph(_escape(str(model.get("title") or "AgentHub 文档")), styles["title"]),
    ]
    if model.get("subtitle"):
        story.append(paragraph(_escape(str(model.get("subtitle"))), styles["subtitle"]))
    story.extend([spacer(1, 20), paragraph(f"模板：{model.get('template') or 'report'} · AgentHub", styles["subtitle"]), page_break()])
    for section in model.get("sections", []):
        if section.get("title"):
            story.append(paragraph(_escape(str(section["title"])), styles["h1"]))
        for block in section.get("blocks", []):
            story.extend(_block_flowables(block, styles, paragraph, page_break, list_flowable, list_item, table, table_style, colors))
    return story


def _block_flowables(block: dict[str, Any], styles, paragraph, page_break, list_flowable, list_item, table, table_style, colors) -> list[Any]:
    block_type = block.get("type")
    if block_type == "heading":
        level = min(max(int(block.get("level") or 2), 1), 3)
        return [paragraph(_escape(str(block.get("text") or "")), styles[f"h{level}"])]
    if block_type == "list":
        items = [list_item(paragraph(_escape(str(item)), styles["base"])) for item in block.get("items", [])]
        bullet_type = "1" if block.get("ordered") else "bullet"
        return [list_flowable(items, bulletType=bullet_type, leftIndent=18)] if items else []
    if block_type == "table":
        return _table_flowable(block, paragraph, styles, table, table_style, colors)
    if block_type == "callout":
        text = f"<b>{_escape(str(block.get('title') or '提示'))}：</b>{_escape(str(block.get('text') or ''))}"
        return [paragraph(text, styles["callout"])]
    if block_type == "page_break":
        return [page_break()]
    return [paragraph(_escape(str(block.get("text") or "")), styles["base"])]


def _table_flowable(block: dict[str, Any], paragraph, styles, table, table_style, colors) -> list[Any]:
    headers = [str(item) for item in block.get("headers", [])]
    rows = [[str(cell) for cell in row] for row in block.get("rows", [])]
    if not headers and not rows:
        return []
    data = [headers] if headers else []
    data.extend(rows)
    flowable = table([[paragraph(_escape(cell), styles["base"]) for cell in row] for row in data], hAlign="LEFT")
    flowable.setStyle(
        table_style(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef6ff")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return [flowable]


def _page_footer(model: dict[str, Any], font_name: str):
    title = str(model.get("title") or "AgentHub")

    def draw(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(font_name, 8.5)
        canvas.setFillColorRGB(0.45, 0.5, 0.56)
        canvas.drawString(document.leftMargin, document.pagesize[1] - 12 * 1.5, f"AgentHub · {title}")
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 14, f"第 {document.page} 页")
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
