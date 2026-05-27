from __future__ import annotations

import json
from typing import Any


ARTIFACT_TOOL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("artifact.create_pdf", ("pdf", "PDF")),
    ("artifact.create_docx", ("word", "docx", "Word", "DOCX")),
    ("artifact.create_xlsx", ("excel", "xlsx", "Excel", "表格")),
    ("artifact.create_pptx", ("ppt", "pptx", "PPT", "幻灯片", "演示文稿")),
    ("artifact.create_html", ("html", "HTML", "网页", "页面")),
)


def detect_artifact_tool(prompt: str) -> str | None:
    text = prompt or ""
    lower = text.lower()
    for tool_name, patterns in ARTIFACT_TOOL_PATTERNS:
        if any(pattern.lower() in lower for pattern in patterns):
            if any(verb in text for verb in ("生成", "创建", "导出", "制作", "写一份", "做一份", "create", "generate", "export")):
                return tool_name
    return None


def select_mock_tool_call(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not tools:
        return None
    user_text = _last_user_text(messages)
    tool_names = _tool_names(tools)
    requested_artifact = detect_artifact_tool(user_text)
    if requested_artifact and requested_artifact in tool_names:
        return _tool_call(requested_artifact, _artifact_arguments(requested_artifact, user_text))
    if "file" in user_text.lower() and "file.extract_text" in tool_names:
        return _tool_call("file.extract_text", {"file_id": "mock-file-id"})
    if any(token in user_text.lower() for token in ("api", "接口")) and "api.test" in tool_names:
        return _tool_call("api.test", {"path": "/api/v1/health", "expected_status": 200})
    if any(token in user_text.lower() for token in ("test", "测试")) and "test.run" in tool_names:
        return _tool_call("test.run", {"command": "pytest --version"})
    return None


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    return next((str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"), "")


def _tool_names(tools: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        if isinstance(function, dict) and function.get("name"):
            names.add(str(function["name"]))
    return names


def _artifact_arguments(tool_name: str, prompt: str) -> dict[str, str]:
    title = prompt.strip().splitlines()[0][:60] or "AgentHub 产物"
    args = {"title": title, "body": prompt}
    if tool_name == "artifact.create_html":
        return {"title": title, "html": f"<main><h1>{title}</h1><p>{prompt}</p></main>"}
    return args


def _tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"call_mock_{tool_name.replace('.', '_')}",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }
