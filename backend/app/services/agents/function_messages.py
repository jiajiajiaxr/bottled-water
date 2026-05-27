from __future__ import annotations

import json
from typing import Any

from app.models import Agent


def agent_system_prompt(
    agent: Agent,
    *,
    mode: str,
    node_title: str | None = None,
    skill_context: str = "",
) -> str:
    base = (agent.config or {}).get("system_prompt") or agent.description or f"你是 {agent.name}。"
    node_hint = f"\n当前工作流节点：{node_title}" if node_title else ""
    return (
        f"{base}{node_hint}\n"
        f"你正在以 {agent.name} 的身份独立执行 {mode}。"
        "你可以根据任务自主决定是否调用已授权的 Tool、Skill 或 MCP。"
        "当用户明确要求生成 PDF、Word、Excel、PPT、HTML/Web 产物时，优先调用对应 artifact.create_* 工具。"
        "生成 PDF 或 Word 时，优先传入结构化 content_model（title、subtitle、sections、"
        "paragraph、heading、list、table、callout、page_break 等），不要只塞一段纯文本。"
        "当用户要求运行测试、检查接口、处理文件、预览页面、部署预览时，优先调用 test.run、api.test、file.*、browser.preview 或 deploy.preview。"
        "如果缺少对应授权，必须说明当前 Agent 没有该工具权限，不能用文字假装已经生成、导出、测试或部署。"
        "没有必要调用工具时可以直接回答。"
        "如果调用了工具，必须结合工具结果继续推理，然后给用户自然语言最终回复。"
        "聊天中的产物卡片、导出入口、部署状态必须来自真实工具结果。"
        "不要伪装成 Master Agent，也不要暴露内部 JSON。"
        f"{skill_context}"
    )


def tool_names(tools: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in tools:
        function = item.get("function") if isinstance(item, dict) else None
        if isinstance(function, dict) and function.get("name"):
            names.add(str(function["name"]))
    return names


def tool_arguments(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"value": value}
    except json.JSONDecodeError:
        return {"raw": raw}
