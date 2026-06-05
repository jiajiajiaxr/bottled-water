from __future__ import annotations

from app.services.external_agents.adapters._cli import CliExternalAgentAdapter


class ClaudeCodeAdapter(CliExternalAgentAdapter):
    name = "claude_code"
    display_name = "Claude Code CLI"
    env_path_name = "CLAUDE_CODE_CLI_PATH"
    env_template_name = "CLAUDE_CODE_CLI_TEMPLATE"
    default_commands = ("claude", "claude-code")
    default_template = ("{command}", "-p", "{prompt}")
    setup_hint = "安装 Claude Code CLI 或设置 CLAUDE_CODE_CLI_PATH；如参数不同，可设置 CLAUDE_CODE_CLI_TEMPLATE。"
    capabilities = ("code_edit", "tests", "shell_commands", "file_changes")
