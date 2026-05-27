from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from app.core.errors import ValidationAppError


SANDBOX_ROOT = Path(__file__).resolve().parents[5] / "var" / "sandboxes"
MAX_TIMEOUT_SECONDS = 30
OUTPUT_LIMIT = 60_000
DENIED_EXECUTABLES = {
    "cmd", "powershell", "pwsh", "bash", "sh", "rm", "del", "erase", "rmdir",
    "rd", "format", "shutdown", "reboot", "reg", "curl", "wget", "ssh", "scp",
}
ALLOWED_EXECUTABLES = {
    "python", "python.exe", "py", "py.exe", "node", "node.exe", "npm", "npm.cmd",
    "pnpm", "pnpm.cmd", "pytest", "pytest.exe", "ruff", "ruff.exe", "uv", "uv.exe",
}
TEST_EXECUTABLES = {"pytest", "ruff", "npm", "pnpm", "uv"}


def resolve_workdir(sandbox_id: str, workdir: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", sandbox_id or "default").strip("-") or "default"
    root = (SANDBOX_ROOT / safe_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / workdir.strip().lstrip("/\\")).resolve() if workdir else root
    if target != root and root not in target.parents:
        raise ValidationAppError("workdir escapes sandbox root")
    target.mkdir(parents=True, exist_ok=True)
    return target


def validate_command_text(command: str) -> None:
    if re.search(r"[\n\r;&|<>`]", command):
        raise ValidationAppError("command contains shell metacharacters")
    if ".." in command or re.search(r"(^|\s)([A-Za-z]:[\\/]|/|~)", command):
        raise ValidationAppError("command contains a path outside the sandbox")


def validate_test_command(command: str) -> None:
    args = shlex.split(command, posix=True)
    if not args:
        raise ValidationAppError("command cannot be empty")
    executable = base_executable(Path(args[0]).name.lower())
    if executable not in TEST_EXECUTABLES:
        raise ValidationAppError("test.run only allows pytest, ruff, npm, pnpm or uv")
    if executable in {"npm", "pnpm"}:
        allowed = len(args) >= 2 and (args[1] == "test" or args[1:3] == ["run", "test"])
        if not allowed:
            raise ValidationAppError("npm/pnpm test.run commands must be test scripts")
    if executable == "uv":
        allowed = len(args) >= 3 and args[1] == "run" and base_executable(args[2]) in {"pytest", "ruff"}
        if not allowed:
            raise ValidationAppError("uv test.run commands must run pytest or ruff")


def base_executable(value: str) -> str:
    return value.removesuffix(".exe").removesuffix(".cmd")


def clean_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value)[:OUTPUT_LIMIT]
