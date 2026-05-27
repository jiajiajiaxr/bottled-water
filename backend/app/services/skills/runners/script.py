from __future__ import annotations

from typing import Any

from app.core.errors import ValidationAppError


async def run_script_skill(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise ValidationAppError("script skill runner requires explicit sandbox/tool authorization")
