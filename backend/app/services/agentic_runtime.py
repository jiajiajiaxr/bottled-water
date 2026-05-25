from __future__ import annotations

import sys

from app.services.agents import tool_loop as _tool_loop

globals().update(_tool_loop.__dict__)
sys.modules[__name__] = _tool_loop
