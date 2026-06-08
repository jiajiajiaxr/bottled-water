from __future__ import annotations

from app.services.external_agents.adapters._cli import CliExternalAgentAdapter


class CodexAdapter(CliExternalAgentAdapter):
    name = "codex"
    display_name = "Codex CLI"
    env_path_name = "CODEX_CLI_PATH"
    env_template_name = "CODEX_CLI_TEMPLATE"
    default_commands = ("codex",)
    default_template = (
        "{command}",
        "exec",
        "--full-auto",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.4-mini",
        "{prompt}",
    )
    setup_hint = "安装 Codex CLI 或设置 CODEX_CLI_PATH；如参数不同，可设置 CODEX_CLI_TEMPLATE。"
    capabilities = ("code_edit", "tests", "shell_commands", "file_changes")
