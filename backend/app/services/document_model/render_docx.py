from __future__ import annotations

import io
from typing import Any

from app.core.errors import ValidationAppError


def render_docx(model: dict[str, Any]) -> bytes:
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt, RGBColor
    except Exception as exc:  # pragma: no cover
        raise ValidationAppError("python-docx is required to generate DOCX artifacts") from exc

    document = Document()
    _configure_document(document, qn, Inches)
    _configure_styles(document, qn, Pt, RGBColor)
    _header_footer(document, model, OxmlElement, qn)
    _cover(document, model, WD_ALIGN_PARAGRAPH)
    for section in model.get("sections", []):
        _render_section(document, section)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _configure_document(document, qn, inches) -> None:
    for section in document.sections:
        section.top_margin = inches(0.75)
        section.bottom_margin = inches(0.72)
        section.left_margin = inches(0.82)
        section.right_margin = inches(0.82)
    settings = document.settings.element
    compat = settings.find(qn("w:compat"))
    if compat is not None:
        compat.set(qn("w:compatSetting"), "true")


def _configure_styles(document, qn, pt_factory, color_factory) -> None:
    font_name = "Microsoft YaHei"
    normal = document.styles["Normal"]
    _style_font(normal, qn, font_name, pt_factory(10.5), color_factory(55, 65, 81))
    for style_name, size in (("Title", 28), ("Heading 1", 20), ("Heading 2", 16), ("Heading 3", 13)):
        _style_font(document.styles[style_name], qn, font_name, pt_factory(size), color_factory(17, 24, 39))
    for style_name in ("List Bullet", "List Number"):
        _style_font(document.styles[style_name], qn, font_name, pt_factory(10.5), color_factory(55, 65, 81))


def _style_font(style, qn, name: str, size, color) -> None:
    style.font.name = name
    style.font.size = size
    style.font.color.rgb = color
    style.element.rPr.rFonts.set(qn("w:eastAsia"), name)


def _header_footer(document, model: dict[str, Any], element_factory, qn) -> None:
    title = str(model.get("title") or "AgentHub 文档")
    for section in document.sections:
        section.header.paragraphs[0].text = f"AgentHub · {title}"
        footer = section.footer.paragraphs[0]
        footer.text = "第 "
        run = footer.add_run()
        fld_begin = element_factory("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        instr = element_factory("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = " PAGE "
        fld_end = element_factory("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        run._r.append(fld_begin)
        run._r.append(instr)
        run._r.append(fld_end)
        footer.add_run(" 页")


def _cover(document, model: dict[str, Any], align) -> None:
    title = document.add_paragraph()
    title.alignment = align.CENTER
    title.style = document.styles["Title"]
    title.add_run(str(model.get("title") or "AgentHub 文档")).bold = True
    subtitle = str(model.get("subtitle") or "")
    if subtitle:
        para = document.add_paragraph(subtitle)
        para.alignment = align.CENTER
    meta = document.add_paragraph(f"模板：{model.get('template') or 'report'} · AgentHub")
    meta.alignment = align.CENTER
    document.add_page_break()


def _render_section(document, section: dict[str, Any]) -> None:
    title = str(section.get("title") or "")
    if title:
        document.add_heading(title, level=int(section.get("level") or 1))
    for block in section.get("blocks", []):
        _render_block(document, block)


def _render_block(document, block: dict[str, Any]) -> None:
    block_type = block.get("type")
    if block_type == "heading":
        document.add_heading(str(block.get("text") or ""), level=int(block.get("level") or 2))
    elif block_type == "list":
        style = "List Number" if block.get("ordered") else "List Bullet"
        for item in block.get("items", []):
            document.add_paragraph(str(item), style=style)
    elif block_type == "table":
        _render_table(document, block)
    elif block_type == "callout":
        para = document.add_paragraph(style="Intense Quote")
        para.add_run(f"{block.get('title') or '提示'}：").bold = True
        para.add_run(str(block.get("text") or ""))
    elif block_type == "page_break":
        document.add_page_break()
    else:
        document.add_paragraph(str(block.get("text") or ""))


def _render_table(document, block: dict[str, Any]) -> None:
    headers = [str(item) for item in block.get("headers", [])]
    rows = [[str(cell) for cell in row] for row in block.get("rows", [])]
    if not headers and not rows:
        return
    column_count = max(len(headers), *(len(row) for row in rows), 1)
    table = document.add_table(rows=1 if headers else 0, cols=column_count)
    table.style = "Table Grid"
    if headers:
        for index, value in enumerate(headers):
            table.rows[0].cells[index].text = value
            for paragraph in table.rows[0].cells[index].paragraphs:
                for run in paragraph.runs:
                    run.bold = True
    for row_values in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row_values[:column_count]):
            cells[index].text = value
