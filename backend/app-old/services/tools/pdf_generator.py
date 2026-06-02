from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

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


def generate_pdf_document(title: str, body: str) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
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
        )
    except Exception as exc:  # pragma: no cover - dependency diagnostics.
        raise ValidationAppError("reportlab is required to generate real PDF artifacts") from exc

    font_name = _register_cjk_font(pdfmetrics, TTFont)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "AgentHubBase",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10.5,
        leading=17,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=7,
    )
    heading = ParagraphStyle(
        "AgentHubHeading",
        parent=base,
        fontSize=18,
        leading=24,
        textColor=colors.HexColor("#111827"),
        spaceBefore=10,
        spaceAfter=10,
    )
    subheading = ParagraphStyle(
        "AgentHubSubHeading",
        parent=base,
        fontSize=13,
        leading=19,
        textColor=colors.HexColor("#111827"),
        spaceBefore=8,
        spaceAfter=6,
    )
    bullet_style = ParagraphStyle("AgentHubBullet", parent=base, leftIndent=8, firstLineIndent=0)

    story = [Paragraph(_escape(title or "AgentHub Document"), heading), Spacer(1, 5 * mm)]
    bullets: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            story.extend(_flush_bullets(bullets, bullet_style, ListFlowable, ListItem, Paragraph))
            story.append(Spacer(1, 3 * mm))
            continue
        if line in {"---", "----", "[pagebreak]"}:
            story.extend(_flush_bullets(bullets, bullet_style, ListFlowable, ListItem, Paragraph))
            story.append(PageBreak())
            continue
        bullet = re.match(r"^([-*+]|\d+[.)])\s+(.+)$", line)
        if bullet:
            bullets.append(bullet.group(2))
            continue
        story.extend(_flush_bullets(bullets, bullet_style, ListFlowable, ListItem, Paragraph))
        if line.startswith("# "):
            story.append(Paragraph(_escape(line[2:]), heading))
        elif line.startswith("## "):
            story.append(Paragraph(_escape(line[3:]), subheading))
        else:
            story.append(Paragraph(_escape(line), base))
    story.extend(_flush_bullets(bullets, bullet_style, ListFlowable, ListItem, Paragraph))
    document.build(story)
    return buffer.getvalue()


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
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        fallback = "STSong-Light"
        pdfmetrics.registerFont(UnicodeCIDFont(fallback))
        return fallback
    except Exception as exc:  # pragma: no cover - host font diagnostics.
        raise ValidationAppError("No usable CJK font found for PDF generation") from exc


def _flush_bullets(
    bullets: list[str],
    bullet_style,
    list_flowable_factory,
    list_item_factory,
    paragraph_factory,
) -> list:
    if not bullets:
        return []
    items = [list_item_factory(paragraph_factory(_escape(item), bullet_style)) for item in bullets]
    bullets.clear()
    return [list_flowable_factory(items, bulletType="bullet", start="circle", leftIndent=18)]


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
