"""Deprecated compatibility shim for model-config LLM gateway helpers.

New code should import from ``app.services.llm.gateway``. This module
intentionally contains no business logic and only preserves legacy imports.
"""

from app.services.llm.gateway import (  # noqa: F401
    stream_model_config,
    stream_model_config_chat,
    test_model_config,
)

__all__ = [
    "stream_model_config",
    "stream_model_config_chat",
    "test_model_config",
]
