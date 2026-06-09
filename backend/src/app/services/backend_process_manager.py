"""Backend service process manager used by deployment preview.

It starts generated FastAPI/Flask-like services in a workspace-scoped
directory so a deployed front-end preview can call a local backend through
AgentHub's deployment proxy.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_BACKEND_PROCESSES = 20
HEALTH_CHECK_TIMEOUT_SECONDS = 30
HEALTH_CHECK_INTERVAL_SECONDS = 1.0


@dataclass
class BackendProcess:
    id: str
    deployment_id: str
    command: str
    cwd: Path
    port: int
    process: subprocess.Popen
    started_at: float = field(default_factory=time.time)
    health_url: str | None = None

    @property
    def is_running(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        if not self.is_running:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)


class BackendProcessManager:
    """Lifecycle manager for generated backend preview processes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: dict[str, BackendProcess] = {}

    def start_backend(
        self,
        *,
        deployment_id: str,
        workspace_dir: Path,
        backend_dir: Path | None = None,
    ) -> BackendProcess | None:
        """Detect and start a backend service inside the workspace directory."""

        with self._lock:
            self._cleanup_stale()
            if len(self._processes) >= MAX_BACKEND_PROCESSES:
                logger.warning("Backend process limit reached: %d", MAX_BACKEND_PROCESSES)
                return None

        entry = self._detect_entry(workspace_dir, backend_dir)
        if not entry:
            logger.info("No backend entry file detected; skip backend preview process")
            return None

        entry_file, backend_path = entry
        port = self._find_free_port()

        req_file = backend_path / "requirements.txt"
        if req_file.exists():
            self._install_requirements(req_file)

        process_id = f"backend_{deployment_id[:8]}"
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    f"{entry_file.stem}:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(port),
                ],
                cwd=str(backend_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            logger.error("Failed to start generated backend process: %s", exc)
            return None

        backend_proc = BackendProcess(
            id=process_id,
            deployment_id=deployment_id,
            command=f"python -m uvicorn {entry_file.stem}:app --port {port}",
            cwd=backend_path,
            port=port,
            process=process,
            health_url=f"http://127.0.0.1:{port}/api/stats",
        )

        if self._wait_for_health(port):
            logger.info("Generated backend started on port=%d pid=%d", port, process.pid)
        else:
            logger.warning("Generated backend startup timed out on port=%d", port)

        with self._lock:
            self._processes[process_id] = backend_proc
        return backend_proc

    def get_backend(self, deployment_id: str) -> BackendProcess | None:
        process_id = f"backend_{deployment_id[:8]}"
        with self._lock:
            proc = self._processes.get(process_id)
            if proc and proc.is_running:
                return proc
            if proc:
                self._processes.pop(process_id, None)
            return None

    def stop_backend(self, deployment_id: str) -> None:
        process_id = f"backend_{deployment_id[:8]}"
        with self._lock:
            proc = self._processes.pop(process_id, None)
        if proc:
            proc.stop()
            logger.info("Generated backend stopped: %s", process_id)

    def stop_all(self) -> None:
        with self._lock:
            processes = list(self._processes.values())
            self._processes.clear()
        for proc in processes:
            proc.stop()

    def _detect_entry(
        self, workspace_dir: Path, backend_dir: Path | None
    ) -> tuple[Path, Path] | None:
        """Return ``(entry_file, backend_path)`` when a backend entry exists."""

        search_dirs: list[Path] = []
        if backend_dir and backend_dir.is_dir():
            search_dirs.append(backend_dir)
        for name in ("backend", "server", "api"):
            candidate = workspace_dir / name
            if candidate.is_dir() and candidate not in search_dirs:
                search_dirs.append(candidate)
        search_dirs.append(workspace_dir)

        for search_dir in search_dirs:
            for entry_name in ("main.py", "app.py", "server.py", "run.py"):
                entry_file = search_dir / entry_name
                if not entry_file.exists():
                    continue
                try:
                    content = entry_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                if any(keyword in content for keyword in ("FastAPI", "Flask", "app = ")):
                    return entry_file, search_dir
        return None

    def _install_requirements(self, req_file: Path) -> None:
        try:
            logger.info("Installing generated backend requirements: %s", req_file)
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(req_file.parent),
                check=False,
            )
        except Exception as exc:
            logger.warning("Generated backend dependency install failed: %s", exc)

    def _find_free_port(self) -> int:
        for port in range(9001, 9100):
            if self._is_port_free(port):
                return port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _is_port_free(port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                sock.bind(("", port))
                return True
        except OSError:
            return False

    def _wait_for_health(self, port: int) -> bool:
        deadline = time.time() + HEALTH_CHECK_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self._is_port_open(port):
                return True
            time.sleep(HEALTH_CHECK_INTERVAL_SECONDS)
        return False

    @staticmethod
    def _is_port_open(port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                return sock.connect_ex(("127.0.0.1", port)) == 0
        except Exception:
            return False

    def _cleanup_stale(self) -> None:
        stale_ids = [process_id for process_id, proc in self._processes.items() if not proc.is_running]
        for process_id in stale_ids:
            self._processes.pop(process_id, None)


BACKEND_PROCESS_MANAGER = BackendProcessManager()
