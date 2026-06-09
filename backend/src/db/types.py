from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Text
from sqlalchemy.types import TypeDecorator

from common.crypto import (
    decrypt_content_leaves,
    decrypt_json,
    decrypt_sensitive_leaves,
    decrypt_text,
    encrypt_content_leaves,
    encrypt_json,
    encrypt_sensitive_leaves,
    encrypt_text,
)


class EncryptedText(TypeDecorator[str]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:  # noqa: ANN001
        if value is None:
            return None
        return encrypt_text(str(value))

    def process_result_value(self, value: Any, dialect) -> Any:  # noqa: ANN001
        if value is None:
            return None
        return decrypt_text(str(value))


class SensitiveJSON(TypeDecorator[Any]):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:  # noqa: ANN001
        return encrypt_sensitive_leaves(value)

    def process_result_value(self, value: Any, dialect) -> Any:  # noqa: ANN001
        return decrypt_sensitive_leaves(value)


class ContentJSON(TypeDecorator[Any]):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:  # noqa: ANN001
        return encrypt_content_leaves(value)

    def process_result_value(self, value: Any, dialect) -> Any:  # noqa: ANN001
        return decrypt_content_leaves(value)


class EncryptedJSON(TypeDecorator[Any]):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:  # noqa: ANN001
        return encrypt_json(value)

    def process_result_value(self, value: Any, dialect) -> Any:  # noqa: ANN001
        return decrypt_json(value)
