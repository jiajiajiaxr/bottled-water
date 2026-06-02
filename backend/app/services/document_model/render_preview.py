from __future__ import annotations

from html import escape
from typing import Any


def render_preview_html(model: dict[str, Any], label: str) -> str:
    cover_html = _cover_html(model, label)
    toc_html = _toc_html(model) if (model.get("toc") or {}).get("enabled", True) else ""
    sections = "".join(_section_html(section) for section in model.get("sections", []))
    appendix = _appendix_html(model.get("appendix") or [])
    signatures = _signatures_html(model.get("signatures") or [])
    return _shell(f"{cover_html}{toc_html}{sections}{appendix}{signatures}")


def _cover_html(model: dict[str, Any], label: str) -> str:
    cover = model.get("cover") or {}
    subtitle = str(cover.get("subtitle") or model.get("subtitle") or "")
    subtitle_html = f"<p class=\"subtitle\">{escape(subtitle)}</p>" if subtitle else ""
    meta = [
        str(cover.get("issuer") or "AgentHub"),
        str(cover.get("confidentiality") or ""),
        f"{cover.get('date_label') or '生成日期'}：{cover.get('date') or ''}",
    ]
    meta_html = "".join(f"<span>{escape(item)}</span>" for item in meta if item)
    template = escape(str(model.get("template") or "report"))
    return f"""
    <main class="page a4-page cover-page template-{template}">
      <div class="label">HTML preview · 下载为真实 {escape(label)} 文件</div>
      <h1>{escape(str(cover.get("title") or model.get("title") or "AgentHub 文档"))}</h1>
      {subtitle_html}
      <div class="cover-meta">{meta_html}</div>
    </main>
    """


def _toc_html(model: dict[str, Any]) -> str:
    title = escape(str((model.get("toc") or {}).get("title") or "目录"))
    items = []
    for index, section in enumerate(model.get("sections", []), start=1):
        if section.get("title"):
            items.append(f"<li><span>{index:02d}</span>{escape(str(section['title']))}</li>")
    return f"""
    <main class="page a4-page toc-page">
      <h2>{title}</h2>
      <ol class="toc">{''.join(items)}</ol>
      <p class="hint">HTML 预览展示结构与排版效果，页码以下载后的 PDF/DOCX 为准。</p>
    </main>
    """


def _section_html(section: dict[str, Any]) -> str:
    title = str(section.get("title") or "")
    title_html = f"<h2>{escape(title)}</h2>" if title else ""
    blocks = "".join(_block_html(block) for block in section.get("blocks", []))
    return f"<main class=\"page a4-page\"><section>{title_html}{blocks}</section></main>"


def _appendix_html(appendix: list[dict[str, Any]]) -> str:
    if not appendix:
        return ""
    sections = "".join(_section_html(section) for section in appendix)
    return f"<div class=\"appendix-label\">附录</div>{sections}"


def _signatures_html(items: list[str]) -> str:
    if not items:
        return ""
    rows = "".join(f"<tr><td>{escape(str(item))}</td><td></td><td></td></tr>" for item in items)
    return f"""
    <main class="page a4-page">
      <h2>签字确认</h2>
      <table><thead><tr><th>角色</th><th>签字</th><th>日期</th></tr></thead><tbody>{rows}</tbody></table>
    </main>
    """


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
    if block_type == "risk_item":
        return _table_html({"headers": ["风险", "级别", "影响", "缓解措施"], "rows": block.get("items") or []})
    if block_type == "action_plan":
        return _table_html({"headers": ["事项", "负责人", "时间", "状态"], "rows": block.get("items") or []})
    if block_type in {"callout", "summary", "conclusion"}:
        title = escape(str(block.get("title") or {"summary": "摘要", "conclusion": "结论"}.get(str(block_type), "提示")))
        text = escape(str(block.get("text") or ""))
        variant = escape(str(block.get("variant") or ("success" if block_type == "conclusion" else "info")))
        return f"<aside class=\"callout {variant}\"><strong>{title}</strong><p>{text}</p></aside>"
    if block_type == "quote":
        return f"<blockquote>{escape(str(block.get('text') or ''))}</blockquote>"
    if block_type == "image":
        alt = escape(str(block.get("alt") or block.get("src") or "未命名图片"))
        return f"<figure class=\"image-placeholder\"><div></div><figcaption>{alt}</figcaption></figure>"
    if block_type == "divider":
        return "<hr>"
    if block_type == "page_break":
        return "<div class=\"page-break\">分页提示</div>"
    if block_type == "signatures":
        return _signatures_html([str(item) for item in block.get("items", [])])
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
.page{{max-width:920px;margin:0 auto 24px;background:white;border:1px solid #dce4ef;border-radius:8px;box-shadow:0 18px 60px rgba(15,23,42,.12)}}
.a4-page{{width:min(794px,100%);min-height:1123px;padding:64px;box-sizing:border-box}}
.cover-page{{display:flex;flex-direction:column;justify-content:center;text-align:center}}
.label{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#1677ff;font-weight:800;margin-bottom:18px}}
h1{{font-size:36px;line-height:1.14;margin:0 0 16px}}.subtitle{{font-size:18px;color:#64748b;margin:0 0 32px}}
.cover-meta{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;color:#64748b}}.cover-meta span{{border:1px solid #e5e7eb;border-radius:999px;padding:6px 12px}}
h2{{font-size:24px;margin:28px 0 12px}}h3{{font-size:19px;margin:22px 0 8px}}h4{{font-size:16px;margin:18px 0 8px}}
p{{line-height:1.85;color:#374151;margin:10px 0}}ul,ol{{padding-left:24px}}li{{margin:7px 0;line-height:1.7}}
.toc{{list-style:none;padding:0}}.toc li{{display:flex;gap:14px;border-bottom:1px dashed #cbd5e1;padding:10px 0}}.toc span{{color:#1677ff;font-weight:800}}
table{{width:100%;border-collapse:collapse;margin:18px 0;table-layout:fixed}}th,td{{border:1px solid #d6deea;padding:10px;vertical-align:top;word-break:break-word}}th{{background:#eef6ff;text-align:left}}
.callout{{border-left:4px solid #1677ff;background:#f0f7ff;padding:12px 16px;margin:16px 0;border-radius:6px}}.callout.warning{{border-color:#f59e0b;background:#fff7ed}}.callout.success{{border-color:#22c55e;background:#f0fdf4}}
blockquote{{border-left:4px solid #cbd5e1;margin:16px 0;padding:8px 16px;color:#475569;background:#f8fafc}}
.image-placeholder{{border:1px dashed #94a3b8;border-radius:8px;padding:20px;text-align:center;color:#64748b}}.image-placeholder div{{height:120px;background:#f8fafc;border-radius:6px;margin-bottom:8px}}
.page-break{{border-top:1px dashed #94a3b8;color:#64748b;text-align:center;margin:26px 0;padding-top:8px}}.hint{{color:#64748b}}.appendix-label{{max-width:920px;margin:8px auto;color:#64748b;font-weight:700}}
hr{{border:none;border-top:1px solid #cbd5e1;margin:24px 0}}
</style></head><body><div class="agenthub-word-preview">{body}</div></body></html>"""
