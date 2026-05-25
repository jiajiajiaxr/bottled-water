from __future__ import annotations

import sys

from app.services.tools import registry as _registry

globals().update(_registry.__dict__)
sys.modules[__name__] = _registry
