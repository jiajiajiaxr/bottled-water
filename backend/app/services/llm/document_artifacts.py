from __future__ import annotations

import re
from typing import Any

from app.services.document_model import normalize_document_model
from app.services.document_model.templates import infer_template_name


DOCUMENT_ARTIFACT_TOOLS = {"artifact.create_pdf", "artifact.create_docx"}


def document_artifact_arguments(prompt: str) -> dict[str, Any]:
    title = _title_from_prompt(prompt)
    template = infer_template_name(title, prompt)
    content_model = normalize_document_model(None, title=title, source_text=prompt, template=template)
    return {
        "title": title,
        "body": prompt,
        "template": template,
        "content_model": content_model,
    }


def normalize_document_artifact_arguments(prompt: str, arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(arguments)
    title = str(normalized.get("title") or _title_from_prompt(prompt)).strip()
    body = str(normalized.get("body") or normalized.get("source_text") or prompt).strip()
    template = str(normalized.get("template") or infer_template_name(title, body, prompt))
    content_model = normalize_document_model(
        normalized.get("content_model"),
        title=title,
        source_text=body,
        template=template,
    )
    normalized.update(
        {
            "title": title,
            "body": body,
            "template": content_model.get("template") or template,
            "content_model": content_model,
        }
    )
    return normalized


def _title_from_prompt(prompt: str) -> str:
    first_line = (prompt or "").strip().splitlines()[0] if (prompt or "").strip() else ""
    cleaned = re.sub(
        r"(请|帮我|麻烦|生成|创建|制作|写一份|写一个|做一份|做一个|导出|pdf|word|docx|文档|报告|方案)",
        "",
        first_line,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ：:，,。.、")
    if cleaned:
        return cleaned[:60]
    template = infer_template_name(prompt)
    labels = {
        "report": "正式报告",
        "proposal": "项目方案",
        "weekly": "工作周报",
        "lab_report": "实验报告",
        "project_plan": "项目计划",
        "prd": "产品需求文档",
        "meeting": "会议纪要",
    }
    return labels.get(template, "AgentHub 正式文档")
