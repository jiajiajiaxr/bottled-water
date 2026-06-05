from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import ok
from app.deps import get_current_user
from app.models import User
from app.services.external_agents.registry import get_external_agent_adapter, list_external_agent_adapters
from app.services.tools.builtins.external_agent import list_recent_external_agent_runs
from db import get_db

router = APIRouter(tags=["external-agents"])


@router.get("/external-agents/probe")
async def probe_external_agents(
    provider: str | None = None,
    user: User = Depends(get_current_user),
):
    del user
    adapters = [get_external_agent_adapter(provider)] if provider else list_external_agent_adapters()
    providers = [adapter.probe().to_dict() for adapter in adapters]
    return ok({"providers": providers, "degraded": [item for item in providers if not item["installed"]]})


@router.post("/external-agents/probe")
async def reprobe_external_agents(
    provider: str | None = None,
    user: User = Depends(get_current_user),
):
    del user
    adapters = [get_external_agent_adapter(provider)] if provider else list_external_agent_adapters()
    providers = [adapter.probe().to_dict() for adapter in adapters]
    return ok({"providers": providers, "degraded": [item for item in providers if not item["installed"]]})


@router.get("/external-agents/runs")
async def external_agent_runs(
    workspace_id: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = await db.run_sync(
        lambda session: list_recent_external_agent_runs(
            session,
            user,
            workspace_id=workspace_id,
            limit=max(1, min(limit, 100)),
        )
    )
    return ok({"items": rows, "total": len(rows)})
