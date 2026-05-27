from __future__ import annotations

import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from app.core.errors import ValidationAppError


SANDBOX_ROOT = Path(__file__).resolve().parents[3] / "var" / "sandboxes"
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


def run_sandbox_command(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command") or "").strip()
    if not command:
        raise ValidationAppError("command cannot be empty")
    timeout = min(max(int(arguments.get("timeout") or 10), 1), MAX_TIMEOUT_SECONDS)
    cwd = _resolve_workdir(str(arguments.get("sandbox_id") or "default"), str(arguments.get("workdir") or ""))
    started = time.perf_counter()
    try:
        result = _run_command(command, cwd=cwd, timeout=timeout, test_mode=False)
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
                "stdout": _clean_output(exc.stdout),
                "stderr": _clean_output(exc.stderr) or f"Timed out after {timeout}s",
                "exit_code": -1,
            },
        )


def run_test_command(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command") or "pytest --version").strip()
    if not command:
        raise ValidationAppError("command cannot be empty")
    _validate_test_command(command)
    started = time.perf_counter()
    timeout = min(max(int(arguments.get("timeout") or 30), 1), MAX_TIMEOUT_SECONDS)
    cwd = _resolve_workdir(str(arguments.get("sandbox_id") or "tests"), str(arguments.get("workdir") or ""))
    try:
        result = _run_command(command, cwd=cwd, timeout=timeout, test_mode=True)
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
                "stdout": _clean_output(exc.stdout),
                "stderr": _clean_output(exc.stderr) or f"Timed out after {timeout}s",
                "exit_code": -1,
            },
        )


def _run_command(command: str, *, cwd: Path, timeout: int, test_mode: bool) -> dict[str, Any]:
    _validate_command_text(command)
    args = shlex.split(command, posix=True)
    if not args:
        raise ValidationAppError("command cannot be empty")
    executable = Path(args[0]).name.lower()
    if command.lower().startswith("echo "):
        return {"stdout": command[5:].strip() + "\n", "stderr": "", "exit_code": 0}
    if executable in {"pwd"}:
        return {"stdout": str(cwd) + "\n", "stderr": "", "exit_code": 0}
    if executable in {"ls"}:
        names = sorted(item.name for item in cwd.iterdir())
        return {"stdout": "\n".join(names) + ("\n" if names else ""), "stderr": "", "exit_code": 0}
    if executable in DENIED_EXECUTABLES or executable not in ALLOWED_EXECUTABLES:
        raise ValidationAppError(f"command executable is not allowed: {args[0]}")
    if test_mode and _base_executable(executable) not in TEST_EXECUTABLES:
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
        "stdout": _clean_output(completed.stdout),
        "stderr": _clean_output(completed.stderr),
        "exit_code": completed.returncode,
    }


def _resolve_workdir(sandbox_id: str, workdir: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", sandbox_id or "default").strip("-") or "default"
    root = (SANDBOX_ROOT / safe_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / workdir.strip().lstrip("/\\")).resolve() if workdir else root
    if target != root and root not in target.parents:
        raise ValidationAppError("workdir escapes sandbox root")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _validate_command_text(command: str) -> None:
    if re.search(r"[\n\r;&|<>`]", command):
        raise ValidationAppError("command contains shell metacharacters")
    if ".." in command or re.search(r"(^|\s)([A-Za-z]:[\\/]|/|~)", command):
        raise ValidationAppError("command contains a path outside the sandbox")


def _validate_test_command(command: str) -> None:
    args = shlex.split(command, posix=True)
    if not args:
        raise ValidationAppError("command cannot be empty")
    executable = _base_executable(Path(args[0]).name.lower())
    if executable not in TEST_EXECUTABLES:
        raise ValidationAppError("test.run only allows pytest, ruff, npm, pnpm or uv")
    if executable in {"npm", "pnpm"}:
        allowed = len(args) >= 2 and (args[1] == "test" or args[1:3] == ["run", "test"])
        if not allowed:
            raise ValidationAppError("npm/pnpm test.run commands must be test scripts")
    if executable == "uv":
        allowed = len(args) >= 3 and args[1] == "run" and _base_executable(args[2]) in {"pytest", "ruff"}
        if not allowed:
            raise ValidationAppError("uv test.run commands must run pytest or ruff")


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


def _base_executable(value: str) -> str:
    return value.removesuffix(".exe").removesuffix(".cmd")


def _clean_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value)[:OUTPUT_LIMIT]
