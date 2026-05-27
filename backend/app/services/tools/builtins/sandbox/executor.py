from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from app.core.errors import ValidationAppError
from app.services.tools.builtins.sandbox.policy import (
    MAX_TIMEOUT_SECONDS,
    clean_output,
    resolve_workdir,
    validate_test_command,
)
from app.services.tools.builtins.sandbox.runner import run_command


def run_sandbox_command(arguments: dict[str, Any]) -> dict[str, Any]:
    command = _command(arguments)
    timeout = _timeout(arguments, default=10)
    cwd = resolve_workdir(str(arguments.get("sandbox_id") or "default"), str(arguments.get("workdir") or ""))
    return _execute(command, cwd=cwd, timeout=timeout, test_mode=False)


def run_test_command(arguments: dict[str, Any]) -> dict[str, Any]:
    command = _command(arguments, default="pytest --version")
    validate_test_command(command)
    timeout = _timeout(arguments, default=30)
    cwd = resolve_workdir(str(arguments.get("sandbox_id") or "tests"), str(arguments.get("workdir") or ""))
    return _execute(command, cwd=cwd, timeout=timeout, test_mode=True)


def _execute(command: str, *, cwd: Path, timeout: int, test_mode: bool) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = run_command(command, cwd=cwd, timeout=timeout, test_mode=test_mode)
        status = "succeeded" if result["exit_code"] == 0 else "failed"
        return _payload(command, status, "real", started, cwd, result)
    except subprocess.TimeoutExpired as exc:
        return _payload(
            command,
            "timeout",
            "real",
            started,
            cwd,
            {
                "stdout": clean_output(exc.stdout),
                "stderr": clean_output(exc.stderr) or f"Timed out after {timeout}s",
                "exit_code": -1,
            },
        )


def _command(arguments: dict[str, Any], *, default: str = "") -> str:
    command = str(arguments.get("command") or default).strip()
    if not command:
        raise ValidationAppError("command cannot be empty")
    return command


def _timeout(arguments: dict[str, Any], *, default: int) -> int:
    return min(max(int(arguments.get("timeout") or default), 1), MAX_TIMEOUT_SECONDS)


def _payload(
    command: str,
    status: str,
    capability_level: str,
    started: float,
    cwd: Path,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "capability_level": capability_level,
        "command": command,
        "cwd": str(cwd),
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
