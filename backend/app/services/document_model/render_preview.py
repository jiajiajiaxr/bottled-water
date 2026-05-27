from __future__ import annotations

from html import escape
from typing import Any


def render_preview_html(model: dict[str, Any], label: str) -> str:
    sections = "".join(_section_html(section) for section in model.get("sections", []))
    subtitle = str(model.get("subtitle") or "")
    subtitle_html = f"<p class=\"subtitle\">{escape(subtitle)}</p>" if subtitle else ""
    return _shell(
        f"""
        <main class="page a4-page template-{escape(str(model.get("template") or "report"))}">
          <header class="cover">
            <div class="label">{escape(label)} Document</div>
            <h1>{escape(str(model.get("title") or "AgentHub 文档"))}</h1>
            {subtitle_html}
          </header>
          {sections}
          <footer>AgentHub · 预览</footer>
        </main>
        """,
    )


def _section_html(section: dict[str, Any]) -> str:
    title = str(section.get("title") or "")
    title_html = f"<h2>{escape(title)}</h2>" if title else ""
    blocks = "".join(_block_html(block) for block in section.get("blocks", []))
    return f"<section>{title_html}{blocks}</section>"


def _block_html(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if block_type == "heading":
        level = min(max(int(block.get("level") or 2), 1), 4)
        return f"<h{level}>{escape(str(block.get('text') or ''))}</h{level}>"
    if block_type == "list":
        tag = "ol" if block.get("ordered") else "ul"
        items = "".join(f"<li>{escape(str(item))}</li>" for item in block.get("items", []))
        return f"<{tag}>{items}</{tag}>"
    if block_type == "table":
        return _table_html(block)
    if block_type == "callout":
        title = escape(str(block.get("title") or "提示"))
        text = escape(str(block.get("text") or ""))
        return f"<aside class=\"callout\"><strong>{title}</strong><p>{text}</p></aside>"
    if block_type == "page_break":
        return "<div class=\"page-break\">分页</div>"
    return f"<p>{escape(str(block.get('text') or ''))}</p>"


def _table_html(block: dict[str, Any]) -> str:
    headers = block.get("headers") if isinstance(block.get("headers"), list) else []
    header_html = "".join(f"<th>{escape(str(cell))}</th>" for cell in headers)
    rows = []
    for row in block.get("rows", []):
        rows.append("".join(f"<td>{escape(str(cell))}</td>" for cell in row))
    body = "".join(f"<tr>{row}</tr>" for row in rows)
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body}</tbody></table>"


def _shell(body: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
body{{margin:0;background:#eef2f7;font-family:Inter,"Microsoft YaHei",system-ui,sans-serif;color:#111827}}
.agenthub-word-preview{{min-height:100vh;padding:32px;box-sizing:border-box}}
.page{{max-width:920px;margin:auto;background:white;border:1px solid #dce4ef;border-radius:8px;box-shadow:0 18px 60px rgba(15,23,42,.12)}}
.a4-page{{width:min(794px,100%);min-height:1123px;padding:64px;box-sizing:border-box}}
.label{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#1677ff;font-weight:800;margin-bottom:18px}}
h1{{font-size:36px;line-height:1.14;margin:0 0 16px}}.subtitle{{font-size:18px;color:#64748b;margin:0 0 32px}}
h2{{font-size:24px;margin:28px 0 12px}}h3{{font-size:19px;margin:22px 0 8px}}h4{{font-size:16px;margin:18px 0 8px}}
p{{line-height:1.85;color:#374151;margin:10px 0}}ul,ol{{padding-left:24px}}li{{margin:7px 0;line-height:1.7}}
table{{width:100%;border-collapse:collapse;margin:18px 0}}th,td{{border:1px solid #d6deea;padding:10px;vertical-align:top}}th{{background:#eef6ff;text-align:left}}
.callout{{border-left:4px solid #1677ff;background:#f0f7ff;padding:12px 16px;margin:16px 0;border-radius:6px}}
.page-break{{border-top:1px dashed #94a3b8;color:#64748b;text-align:center;margin:26px 0;padding-top:8px}}
footer{{margin-top:42px;padding-top:16px;border-top:1px solid #e5e7eb;color:#94a3b8;font-size:12px}}
</style></head><body><div class="agenthub-word-preview">{body}</div></body></html>"""
