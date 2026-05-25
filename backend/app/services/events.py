from __future__ import annotations

import sys

from app.services.realtime import event_bus as _event_bus

globals().update(_event_bus.__dict__)
sys.modules[__name__] = _event_bus
