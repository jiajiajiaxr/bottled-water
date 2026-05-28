from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from app.core.errors import ValidationAppError
from app.services.tools.builtins.sandbox.policy import (
    ALLOWED_EXECUTABLES,
    DENIED_EXECUTABLES,
    TEST_EXECUTABLES,
    base_executable,
    clean_output,
    validate_command_text,
)


def run_command(command: str, *, cwd: Path, timeout: int, test_mode: bool) -> dict[str, Any]:
    validate_command_text(command)
    args = shlex.split(command, posix=True)
    if not args:
        raise ValidationAppError("command cannot be empty")
    executable = Path(args[0]).name.lower()
    if executable in DENIED_EXECUTABLES or executable not in ALLOWED_EXECUTABLES:
        raise ValidationAppError(f"command executable is not allowed: {args[0]}")
    if test_mode and base_executable(executable) not in TEST_EXECUTABLES:
        raise ValidationAppError("test.run only allows pytest, ruff, npm, pnpm or uv test commands")
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "stdout": clean_output(completed.stdout),
        "stderr": clean_output(completed.stderr),
        "exit_code": completed.returncode,
    }
