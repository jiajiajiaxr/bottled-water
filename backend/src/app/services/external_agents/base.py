from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.models import ExternalAgentRun, User


@dataclass(frozen=True)
class ExternalAgentProbe:
    provider: str
    installed: bool
    command_path: str | None
    command_source: str
    reason: str | None = None
    setup_hint: str = ""
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "installed": self.installed,
            "command_path": self.command_path,
            "command_source": self.command_source,
            "reason": self.reason,
            "setup_hint": self.setup_hint,
            "capabilities": self.capabilities,
        }


@dataclass(frozen=True)
class ExternalAgentRunRequest:
    provider: str
    prompt: str
    workspace_id: str | None
    conversation_id: str | None
    agent_id: str | None
    cwd: Path
    timeout_ms: int = 120_000
    wait: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ExternalAgentAdapter(Protocol):
    name: str
    display_name: str
    capabilities: tuple[str, ...]

    def probe(self) -> ExternalAgentProbe:
        ...

    def start_run(
        self,
        db: Any,
        *,
        user: User,
        request: ExternalAgentRunRequest,
    ) -> dict[str, Any]:
        ...

    def cancel_run(self, db: Any, *, user: User, run: ExternalAgentRun) -> dict[str, Any]:
        ...

    def stream_events(self, run: ExternalAgentRun) -> list[dict[str, Any]]:
        ...
