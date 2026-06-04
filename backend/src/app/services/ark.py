"""Deprecated compatibility shim for the Ark LLM client.

New code should import from ``app.services.llm.ark``. This module intentionally
contains no business logic and only preserves legacy imports.
"""

from app.services.llm.ark import (  # noqa: F401
    ArkClient,
    ArkProviderError,
    LLMResult,
    LLMStreamEvent,
    ark_client,
    extract_output_text,
)

__all__ = [
    "ArkClient",
    "ArkProviderError",
    "LLMResult",
    "LLMStreamEvent",
    "ark_client",
    "extract_output_text",
]
