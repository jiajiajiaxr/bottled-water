"""Deprecated compatibility shim for the historical tool registry module.

New code must import from ``app.services.tools.catalog``,
``app.services.tools.executor`` and ``app.services.tools.permissions``.
Legacy awaitable adapters live in ``app.services.tools.legacy_registry``.
"""

from app.services.tools.legacy_registry import *  # noqa: F403
