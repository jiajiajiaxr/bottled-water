"""Deprecated compatibility shim for the old tool registry module.

New code must import from ``app.services.tools``:

- catalog: tool directory and database synchronization
- executor: runtime dispatch and invocation records
- permissions: normalization and permission checks
- builtins: code-backed built-in tool implementations

This module only preserves legacy imports while migration tests and older
adapters still refer to ``app.services.tool_registry``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import User
from app.services.tools.builtins.executor import invoke_builtin_tool as _invoke_builtin_tool
from app.services.tools.builtins.registry import BUILTIN_TOOLS, BuiltinTool
from app.services.tools.catalog import (
    ensure_tool_tables as _ensure_tool_tables,
    get_custom_tool as _get_custom_tool,
    get_tool_definition as _get_tool_definition,
    list_tools as _list_tools,
    sync_builtin_tool_definitions as _sync_builtin_tool_definitions,
)
from app.services.tools.executor import invoke_tool as _invoke_tool
from app.services.tools.permissions import normalize_tool_names
from app.services.tools.toolboxes import TOOLBOXES, get_official_toolbox


async def _run_sync(db: AsyncSession | Session, fn):
    if isinstance(db, AsyncSession):
        return await db.run_sync(fn)
    return fn(db)


def builtin_tool_dicts() -> list[dict[str, Any]]:
    return [tool.to_dict() for tool in BUILTIN_TOOLS.values()]


async def ensure_tool_tables(db: AsyncSession | Session) -> None:
    await _run_sync(db, _ensure_tool_tables)


async def sync_builtin_tool_definitions(db: AsyncSession | Session) -> None:
    await _run_sync(db, _sync_builtin_tool_definitions)


async def list_tools(
    db: AsyncSession | Session,
    user: User,
    *,
    workspace_id: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    return await _run_sync(
        db,
        lambda session: _list_tools(
            session,
            user,
            workspace_id=workspace_id,
            q=q,
        ),
    )


async def get_custom_tool(db: AsyncSession | Session, user: User, tool_id_or_name: str):
    return await _run_sync(db, lambda session: _get_custom_tool(session, user, tool_id_or_name))


async def get_tool_definition(db: AsyncSession | Session, user: User, tool_id_or_name: str):
    return await _run_sync(
        db,
        lambda session: _get_tool_definition(session, user, tool_id_or_name),
    )


async def invoke_builtin_tool(
    db: AsyncSession | Session,
    user: User,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return await _run_sync(db, lambda session: _invoke_builtin_tool(session, user, name, arguments))


async def invoke_tool(
    db: AsyncSession | Session,
    user: User,
    tool_id_or_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return await _run_sync(
        db,
        lambda session: _invoke_tool(session, user, tool_id_or_name, arguments),
    )


__all__ = [
    "BUILTIN_TOOLS",
    "TOOLBOXES",
    "BuiltinTool",
    "builtin_tool_dicts",
    "ensure_tool_tables",
    "get_custom_tool",
    "get_official_toolbox",
    "get_tool_definition",
    "invoke_builtin_tool",
    "invoke_tool",
    "list_tools",
    "normalize_tool_names",
    "sync_builtin_tool_definitions",
]
