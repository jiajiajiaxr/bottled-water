from __future__ import annotations

import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.models import ExternalAgentRun, User, utcnow
from app.services.external_agents.base import ExternalAgentProbe, ExternalAgentRunRequest
from app.services.external_agents.events import redact_secrets, summarize_events
from app.services.external_agents.process_manager import ProcessResult, process_manager
from app.services.external_agents.workspace import changed_files, snapshot_files


class CliExternalAgentAdapter:
    name: str
    display_name: str
    env_path_name: str
    env_template_name: str
    default_commands: tuple[str, ...]
    default_template: tuple[str, ...]
    setup_hint: str
    capabilities: tuple[str, ...] = ("code_edit", "shell_commands", "file_changes")

    def probe(self) -> ExternalAgentProbe:
        command_path, source = self._command_path()
        installed = bool(command_path)
        return ExternalAgentProbe(
            provider=self.name,
            installed=installed,
            command_path=command_path,
            command_source=source,
            reason=None if installed else "command_not_found",
            setup_hint="" if installed else self.setup_hint,
            capabilities=list(self.capabilities),
        )

    def start_run(
        self,
        db: Session,
        *,
        user: User,
        request: ExternalAgentRunRequest,
    ) -> dict[str, Any]:
        probe = self.probe()
        run = ExternalAgentRun(
            provider=self.name,
            owner_id=user.id,
            workspace_id=request.workspace_id,
            conversation_id=request.conversation_id,
            agent_id=request.agent_id,
            status="running" if probe.installed else "degraded",
            command=[],
            cwd=str(request.cwd),
            input_prompt=redact_secrets(request.prompt),
            stdout_tail="",
            stderr_tail="",
            changed_files=[],
            started_at=utcnow(),
            extra={"events": [], "metadata": request.metadata, "probe": probe.to_dict()},
        )
        db.add(run)
        db.flush()

        if not probe.installed or not probe.command_path:
            run.status = "degraded"
            run.completed_at = utcnow()
            run.error = probe.reason or "command_not_found"
            run.extra = {
                **(run.extra or {}),
                "events": [
                    {
                        "type": "failed",
                        "provider": self.name,
                        "run_id": run.id,
                        "message": run.error,
                        "data": {"setup_hint": probe.setup_hint},
                    }
                ],
            }
            db.flush()
            return self.run_payload(run)

        argv = self._argv(probe.command_path, request.prompt)
        run.command = _redact_argv(argv)
        before = snapshot_files(request.cwd)

        if not request.wait:
            process_manager.start(run_id=run.id, provider=self.name, argv=argv, cwd=request.cwd)
            run.extra = {**(run.extra or {}), "events": process_manager.events(run.id)}
            db.flush()
            return self.run_payload(run)

        result = process_manager.run(
            run_id=run.id,
            provider=self.name,
            argv=argv,
            cwd=request.cwd,
            timeout_ms=request.timeout_ms,
        )
        self._finish_run(db, run, result, changed_files(request.cwd, before))
        return self.run_payload(run)

    def cancel_run(self, db: Session, *, user: User, run: ExternalAgentRun) -> dict[str, Any]:
        self._ensure_access(user, run)
        result = process_manager.cancel(run.id)
        if result:
            self._finish_run(db, run, result, run.changed_files or [])
            return self.run_payload(run)
        if run.status in {"completed", "failed", "cancelled", "degraded"}:
            return self.run_payload(run)
        run.status = "cancelled"
        run.completed_at = utcnow()
        run.error = "run is not active in this process"
        db.flush()
        return self.run_payload(run)

    def stream_events(self, run: ExternalAgentRun) -> list[dict[str, Any]]:
        live = process_manager.events(run.id)
        if live:
            return live
        events = (run.extra or {}).get("events")
        return events if isinstance(events, list) else []

    def run_payload(self, run: ExternalAgentRun) -> dict[str, Any]:
        return {
            "status": run.status,
            "provider": run.provider,
            "run_id": run.id,
            "cwd": run.cwd,
            "events": summarize_events(self.stream_events(run)),
            "changed_files": run.changed_files or [],
            "stdout_tail": run.stdout_tail,
            "stderr_tail": run.stderr_tail,
            "exit_code": run.exit_code,
            "duration_ms": run.duration_ms,
            "error": run.error,
        }

    def _finish_run(
        self,
        db: Session,
        run: ExternalAgentRun,
        result: ProcessResult,
        files_changed: list[dict[str, Any]],
    ) -> None:
        run.status = result.status
        run.stdout_tail = result.stdout_tail
        run.stderr_tail = result.stderr_tail
        run.exit_code = result.exit_code
        run.duration_ms = result.duration_ms
        run.error = result.error
        run.changed_files = files_changed
        run.completed_at = utcnow()
        run.extra = {**(run.extra or {}), "events": summarize_events(result.events, limit=80)}
        db.flush()

    def _command_path(self) -> tuple[str | None, str]:
        explicit = os.getenv(self.env_path_name)
        if explicit:
            path = Path(explicit).expanduser()
            return (str(path), f"env:{self.env_path_name}") if path.exists() else (None, f"env:{self.env_path_name}")
        for command in self.default_commands:
            found = shutil.which(command)
            if found:
                return found, "PATH"
        return None, "PATH"

    def _argv(self, command_path: str, prompt: str) -> list[str]:
        template = self._template()
        argv = [
            token.replace("{command}", command_path).replace("{prompt}", prompt)
            for token in template
        ]
        if not any("{prompt}" in token for token in template):
            argv.append(prompt)
        if not argv or argv[0] != command_path:
            argv.insert(0, command_path)
        return argv

    def _template(self) -> list[str]:
        raw = os.getenv(self.env_template_name)
        if raw:
            stripped = raw.strip()
            if stripped.startswith("["):
                value = json.loads(stripped)
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    return value
            return shlex.split(stripped)
        return list(self.default_template)

    def _ensure_access(self, user: User, run: ExternalAgentRun) -> None:
        if user.role == "admin" or run.owner_id == user.id:
            return
        raise ForbiddenError("无权访问外部 Agent 运行记录")


def _redact_argv(argv: list[str]) -> list[str]:
    return [redact_secrets(item) for item in argv]


def get_run_for_user(db: Session, user: User, run_id: str) -> ExternalAgentRun:
    run = db.get(ExternalAgentRun, run_id)
    if not run or run.deleted_at is not None:
        raise NotFoundError("外部 Agent 运行记录不存在")
    if user.role != "admin" and run.owner_id != user.id:
        raise ForbiddenError("无权访问外部 Agent 运行记录")
    return run
