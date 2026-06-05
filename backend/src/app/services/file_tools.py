"""Deprecated compatibility shim for file tool helpers.

New code should import from ``app.services.tools.builtins.file``. This module
intentionally contains no business logic and only preserves legacy imports.
"""

from app.services.tools.builtins.file.converters import (  # noqa: F401
    GeneratedFile,
    convert_file,
    generate_docx,
    generate_file,
    generate_html,
    generate_markdown,
    generate_pdf,
    generate_pptx,
    generate_xlsx,
    generate_zip,
)
from app.services.tools.builtins.file.extractors import (  # noqa: F401
    embed_text,
    extract_text_from_path,
    summarize_text,
)
from app.services.tools.builtins.file.preview import preview_payload  # noqa: F401

__all__ = [
    "GeneratedFile",
    "convert_file",
    "embed_text",
    "extract_text_from_path",
    "generate_docx",
    "generate_file",
    "generate_html",
    "generate_markdown",
    "generate_pdf",
    "generate_pptx",
    "generate_xlsx",
    "generate_zip",
    "preview_payload",
    "summarize_text",
]
