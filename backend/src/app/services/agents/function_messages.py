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
        f"你正在以 {agent.name} 的身份独立执行 {mode}。\n"
        "你可以根据任务自主决定是否调用已授权的 Tool、Skill 或 MCP。\n"
        "当用户明确要求生成 PDF、Word、Excel、PPT、HTML/Web 产物时，优先调用对应 artifact.create_* 工具。\n"
        "如果用户说“再生成一个”“重新生成”“生成一个新的”“再来一个示例”等创建语义，必须再次调用 artifact.create_* 创建全新的产物和预览卡片。\n"
        "只有当用户明确说“修改、补充、更新、改上一个产物、改上一版、在刚才的产物上调整”时，才调用 artifact.revise 更新旧产物。\n"
        "生成 PDF 或 Word 时，优先传入结构化 content_model，不要只填一段纯文本；content_model 应包含 template、cover、toc、metadata、sections、blocks，"
        "blocks 可用 paragraph、heading、list、table、callout、quote、image、divider、page_break。\n"
        "如果用户只说生成报告/方案/PRD/会议纪要/实验报告，请自动选择 report、proposal、prd、meeting、lab_report 模板，并补齐正式章节。\n"
        "当用户要求运行测试、检查接口、处理文件、预览页面或部署预览时，优先调用 test.run、api.test、file.*、browser.preview 或 deploy.preview。\n"
        "如果缺少对应授权，必须说明当前 Agent 没有该工具权限，不能用文字假装已经生成、导出、测试或部署。\n"
        "没有必要调用工具时可以直接回答。\n"
        "如果调用了工具，必须结合工具结果继续推理，然后给用户自然语言最终回复。\n"
        "聊天里的产物卡片、导出入口和部署状态必须来自真实工具结果。\n"
        "不要伪装成 Master Agent，也不要暴露内部 JSON。\n"
        "For interactive CLI wizards or scaffolding (create-vue, npm init, npx shadcn init, install prompts), "
        "use terminal.start, terminal.wait_for, terminal.send, and terminal.snapshot/terminal.stop; "
        "use sandbox.run only for non-interactive one-shot commands.\n"
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
