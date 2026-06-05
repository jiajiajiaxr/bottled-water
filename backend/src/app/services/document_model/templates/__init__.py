from app.services.document_model.templates.registry import (
    DOCUMENT_TEMPLATES,
    DocumentTemplate,
    available_templates,
    get_template,
    normalize_template_name,
)

__all__ = [
    "DOCUMENT_TEMPLATES",
    "DocumentTemplate",
    "available_templates",
    "get_template",
    "normalize_template_name",
]
