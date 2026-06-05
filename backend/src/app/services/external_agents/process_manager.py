from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.external_agents.events import external_agent_event, redact_secrets, tail_text


@dataclass
class ProcessResult:
    status: str
    events: list[dict[str, Any]]
    stdout_tail: str
    stderr_tail: str
    exit_code: int | None
    duration_ms: int
    error: str | None = None


@dataclass
class ActiveExternalProcess:
    run_id: str
    provider: str
    process: subprocess.Popen[str]
    events: list[dict[str, Any]] = field(default_factory=list)
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)
    reader_threads: list[threading.Thread] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    cancelled: bool = False


class ExternalAgentProcessManager:
    def __init__(self) -> None:
        self._active: dict[str, ActiveExternalProcess] = {}
        self._lock = threading.Lock()

    def run(
        self,
        *,
        run_id: str,
        provider: str,
        argv: list[str],
        cwd: Path,
        timeout_ms: int,
    ) -> ProcessResult:
        self.start(run_id=run_id, provider=provider, argv=argv, cwd=cwd)
        return self.wait(run_id, timeout_ms=timeout_ms)

    def start(
        self,
        *,
        run_id: str,
        provider: str,
        argv: list[str],
        cwd: Path,
    ) -> ActiveExternalProcess:
        if not argv or not argv[0]:
            raise ValueError("external agent command is empty")
        cwd.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "NO_COLOR": "1",
        }
        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=env,
        )
        active = ActiveExternalProcess(
            run_id=run_id,
            provider=provider,
            process=process,
            events=[external_agent_event("started", provider=provider, run_id=run_id, data={"pid": process.pid})],
        )
        with self._lock:
            self._active[run_id] = active
        self._start_reader(active, "stdout")
        self._start_reader(active, "stderr")
        return active

    def wait(self, run_id: str, *, timeout_ms: int) -> ProcessResult:
        active = self._get(run_id)
        try:
            exit_code = active.process.wait(timeout=max(1, timeout_ms) / 1000)
        except subprocess.TimeoutExpired:
            active.cancelled = True
            self._terminate(active)
            duration_ms = int((time.perf_counter() - active.started) * 1000)
            self._join_readers(active)
            result = ProcessResult(
                status="failed",
                events=[
                    *active.events,
                    external_agent_event(
                        "failed",
                        provider=active.provider,
                        run_id=run_id,
                        message="external agent timeout",
                    ),
                ],
                stdout_tail=tail_text(active.stdout_lines),
                stderr_tail=tail_text(active.stderr_lines),
                exit_code=None,
                duration_ms=duration_ms,
                error="timeout",
            )
            self._remove(run_id)
            return result

        duration_ms = int((time.perf_counter() - active.started) * 1000)
        self._join_readers(active)
        status = "cancelled" if active.cancelled else ("completed" if exit_code == 0 else "failed")
        event_type = "cancelled" if active.cancelled else ("completed" if exit_code == 0 else "failed")
        error = None if status == "completed" else tail_text(active.stderr_lines, limit=1200) or f"exit_code={exit_code}"
        result = ProcessResult(
            status=status,
            events=[
                *active.events,
                external_agent_event(
                    event_type,
                    provider=active.provider,
                    run_id=run_id,
                    data={"exit_code": exit_code, "duration_ms": duration_ms},
                    message=error or "",
                ),
            ],
            stdout_tail=tail_text(active.stdout_lines),
            stderr_tail=tail_text(active.stderr_lines),
            exit_code=exit_code,
            duration_ms=duration_ms,
            error=redact_secrets(error) if error else None,
        )
        self._remove(run_id)
        return result

    def cancel(self, run_id: str) -> ProcessResult | None:
        active = self._active.get(run_id)
        if not active:
            return None
        active.cancelled = True
        self._terminate(active)
        return self.wait(run_id, timeout_ms=3000)

    def events(self, run_id: str) -> list[dict[str, Any]]:
        active = self._active.get(run_id)
        return list(active.events) if active else []

    def _start_reader(self, active: ActiveExternalProcess, stream_name: str) -> None:
        stream = active.process.stdout if stream_name == "stdout" else active.process.stderr
        target_lines = active.stdout_lines if stream_name == "stdout" else active.stderr_lines
        if stream is None:
            return

        def _reader() -> None:
            for line in stream:
                clean = redact_secrets(line.rstrip("\n"))
                target_lines.append(clean)
                active.events.append(
                    external_agent_event(
                        "delta",
                        provider=active.provider,
                        run_id=active.run_id,
                        message=clean,
                        data={"stream": stream_name},
                    )
                )

        thread = threading.Thread(target=_reader, name=f"external-agent-{active.run_id}-{stream_name}", daemon=True)
        active.reader_threads.append(thread)
        thread.start()

    def _terminate(self, active: ActiveExternalProcess) -> None:
        if active.process.poll() is not None:
            return
        active.process.terminate()
        try:
            active.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            active.process.kill()

    def _get(self, run_id: str) -> ActiveExternalProcess:
        with self._lock:
            active = self._active.get(run_id)
        if not active:
            raise KeyError(f"external agent run is not active: {run_id}")
        return active

    def _remove(self, run_id: str) -> None:
        with self._lock:
            self._active.pop(run_id, None)

    @staticmethod
    def _join_readers(active: ActiveExternalProcess) -> None:
        for thread in active.reader_threads:
            thread.join(timeout=0.2)


process_manager = ExternalAgentProcessManager()
