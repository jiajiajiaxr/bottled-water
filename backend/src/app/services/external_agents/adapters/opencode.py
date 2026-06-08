from __future__ import annotations

from app.services.external_agents.adapters._cli import CliExternalAgentAdapter


class OpenCodeAdapter(CliExternalAgentAdapter):
    name = "opencode"
    display_name = "OpenCode CLI"
    env_path_name = "OPENCODE_CLI_PATH"
    env_template_name = "OPENCODE_CLI_TEMPLATE"
    default_commands = ("opencode", "open-code")
    default_template = ("{command}", "run", "{prompt}")
    setup_hint = (
        "安装 OpenCode CLI 或设置 OPENCODE_CLI_PATH；"
        "如参数不同，可设置 OPENCODE_CLI_TEMPLATE。"
    )
    capabilities = ("code_edit", "tests", "shell_commands", "file_changes")
