from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


TEXT_PREFIX = "enc:v1:"
BYTES_PREFIX = b"AGENTHUB-ENC-v1:"
JSON_MARKER = "__agenthub_encrypted_json__"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "bearer",
    "code",
    "directive",
    "guardrail",
    "instruction",
    "instructions",
    "policy",
    "policies",
    "prompt",
    "secret",
    "rule",
    "rules",
    "source_code",
    "token",
    "password",
    "authorization",
    "credential",
    "private_key",
    "access_key",
    "system_prompt",
)
CONTENT_KEY_PARTS = (
    "answer",
    "body",
    "change_summary",
    "code",
    "command",
    "content",
    "deploy_log",
    "description",
    "error",
    "error_message",
    "extracted_text",
    "html",
    "input",
    "input_prompt",
    "markdown",
    "message",
    "output",
    "preview_html",
    "prompt",
    "query",
    "raw_preview",
    "reason",
    "response",
    "result",
    "source_text",
    "stderr",
    "stderr_tail",
    "stdout",
    "stdout_tail",
    "summary",
    "text",
    "thinking",
    "title",
    "user_input",
    "work_product",
)
CONTENT_DESCENDANT_KEYS = (
    "attachments",
    "chunks",
    "events",
    "files",
    "messages",
    "previous_files",
    "runtime_report",
    "status_report",
    "tool_events",
    "transcript",
)
STRUCTURAL_KEY_PARTS = (
    "artifact_id",
    "checksum",
    "client_message_id",
    "content_type",
    "conversation_id",
    "download_url",
    "duration_ms",
    "export_url",
    "file_asset_id",
    "filename",
    "format",
    "id",
    "media_type",
    "mime_type",
    "original_filename",
    "path",
    "preview_pdf_url",
    "preview_url",
    "public_url",
    "role",
    "size",
    "status",
    "storage_path",
    "stream_message_id",
    "type",
    "url",
    "version",
    "workspace_id",
)


def encryption_enabled() -> bool:
    return True


def encrypt_text(value: str) -> str:
    if not value or is_encrypted_text(value):
        return value
    nonce = secrets.token_bytes(12)
    cipher = _aesgcm().encrypt(nonce, value.encode("utf-8"), _key_id().encode("utf-8"))
    return f"{TEXT_PREFIX}{_key_id()}:{_b64(nonce + cipher)}"


def decrypt_text(value: str) -> str:
    if not is_encrypted_text(value):
        return value
    try:
        _prefix, _version, key_id, payload = value.split(":", 3)
        raw = _b64decode(payload)
        nonce, cipher = raw[:12], raw[12:]
        return _aesgcm().decrypt(nonce, cipher, key_id.encode("utf-8")).decode("utf-8")
    except Exception:
        return value


def is_encrypted_text(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(TEXT_PREFIX)


def encrypt_json(value: Any) -> Any:
    if value is None:
        return None
    if _is_encrypted_json_wrapper(value):
        return value
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return {JSON_MARKER: encrypt_text(payload)}


def decrypt_json(value: Any) -> Any:
    if _is_encrypted_json_wrapper(value):
        decrypted = decrypt_text(str(value.get(JSON_MARKER) or ""))
        try:
            return json.loads(decrypted)
        except json.JSONDecodeError:
            return value
    return decrypt_sensitive_leaves(value)


def encrypt_sensitive_leaves(value: Any) -> Any:
    return _walk_sensitive(value, path=(), encrypt=True)


def decrypt_sensitive_leaves(value: Any) -> Any:
    return _walk_sensitive(value, path=(), encrypt=False)


def encrypt_content_leaves(value: Any) -> Any:
    return _walk_content(value, path=(), encrypt=True)


def decrypt_content_leaves(value: Any) -> Any:
    return _walk_content(value, path=(), encrypt=False)


def encrypt_file_bytes(raw: bytes) -> bytes:
    if raw.startswith(BYTES_PREFIX):
        return raw
    nonce = secrets.token_bytes(12)
    cipher = _aesgcm().encrypt(nonce, raw, _key_id().encode("utf-8"))
    return BYTES_PREFIX + _key_id().encode("utf-8") + b":" + _b64(nonce + cipher).encode("ascii")


def decrypt_file_bytes(raw: bytes) -> bytes:
    if not raw.startswith(BYTES_PREFIX):
        return raw
    try:
        remainder = raw[len(BYTES_PREFIX) :]
        key_id_raw, payload_raw = remainder.split(b":", 1)
        payload = _b64decode(payload_raw.decode("ascii"))
        nonce, cipher = payload[:12], payload[12:]
        return _aesgcm().decrypt(nonce, cipher, key_id_raw)
    except Exception:
        return raw


def write_encrypted_file(path: Path, raw: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_file_bytes(raw))
    return encryption_metadata(raw_size=len(raw))


def read_encrypted_file(path: Path) -> bytes:
    return decrypt_file_bytes(path.read_bytes())


def encryption_metadata(*, raw_size: int | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "status": "encrypted",
        "algorithm": "AES-256-GCM",
        "key_id": _key_id(),
    }
    if raw_size is not None:
        metadata["plaintext_size"] = raw_size
    return metadata


def is_file_encrypted(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(BYTES_PREFIX)) == BYTES_PREFIX
    except OSError:
        return False


@contextmanager
def materialized_plaintext_file(path: Path, *, suffix: str = "") -> Iterator[Path]:
    if not is_file_encrypted(path):
        yield path
        return
    raw = read_encrypted_file(path)
    fd, temp_name = tempfile.mkstemp(prefix="agenthub-dec-", suffix=suffix)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        yield temp_path
    finally:
        temp_path.unlink(missing_ok=True)


def _is_encrypted_json_wrapper(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {JSON_MARKER} and is_encrypted_text(value.get(JSON_MARKER))


def _walk_sensitive(value: Any, *, path: tuple[str, ...], encrypt: bool) -> Any:
    return _walk_strings(value, path=path, encrypt=encrypt, should_encrypt=_is_sensitive_path)


def _walk_content(value: Any, *, path: tuple[str, ...], encrypt: bool) -> Any:
    return _walk_strings(value, path=path, encrypt=encrypt, should_encrypt=_is_content_path)


def _walk_strings(
    value: Any,
    *,
    path: tuple[str, ...],
    encrypt: bool,
    should_encrypt: Callable[[tuple[str, ...]], bool],
) -> Any:
    if isinstance(value, dict):
        return {
            key: _walk_strings(
                item,
                path=(*path, str(key)),
                encrypt=encrypt,
                should_encrypt=should_encrypt,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _walk_strings(item, path=path, encrypt=encrypt, should_encrypt=should_encrypt)
            for item in value
        ]
    if isinstance(value, str):
        if not encrypt and is_encrypted_text(value):
            return decrypt_text(value)
        if encrypt and should_encrypt(path):
            return encrypt_text(value)
    return value


def _is_sensitive_path(path: tuple[str, ...]) -> bool:
    lowered = ".".join(path).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _is_content_path(path: tuple[str, ...]) -> bool:
    lowered = ".".join(path).lower()
    leaf = path[-1].lower() if path else ""
    if _is_structural_path(path):
        return False
    return (
        any(part in lowered for part in SENSITIVE_KEY_PARTS)
        or any(part in leaf for part in CONTENT_KEY_PARTS)
        or any(part in lowered.split(".") for part in CONTENT_DESCENDANT_KEYS)
    )


def _is_structural_path(path: tuple[str, ...]) -> bool:
    leaf = path[-1].lower() if path else ""
    return (
        leaf in STRUCTURAL_KEY_PARTS
        or leaf.endswith("_id")
        or leaf.endswith("_ids")
        or leaf.endswith("_url")
        or leaf.endswith("_path")
        or leaf.endswith("_type")
        or leaf.endswith("_at")
    )


def _aesgcm() -> AESGCM:
    return AESGCM(_key_bytes())


def _key_bytes() -> bytes:
    raw = _setting("data_encryption_key") or ""
    if raw:
        decoded = _decode_configured_key(raw)
        if decoded:
            return decoded
    return hashlib.sha256((_setting("secret_key") or "agenthub-dev-secret-change-me").encode("utf-8")).digest()


def _setting(name: str) -> str | None:
    env_name = "".join(f"_{char}" if char.isupper() else char for char in name).upper()
    value = os.getenv(env_name)
    if value is not None:
        return value
    return _dotenv_settings().get(name) or _dotenv_settings().get(env_name)


@lru_cache
def _dotenv_settings() -> dict[str, str]:
    values: dict[str, str] = {}
    repo_root = Path(__file__).resolve().parents[3]
    for path in (repo_root / ".env", repo_root / "backend" / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            key = key.strip()
            value = raw_value.strip().strip("'\"")
            values[key] = value
            values[key.lower()] = value
    return values


def _decode_configured_key(raw: str) -> bytes | None:
    normalized = raw.strip()
    if len(normalized) in {32, 48, 64}:
        try:
            decoded = bytes.fromhex(normalized)
            if len(decoded) in {16, 24, 32}:
                return decoded
        except ValueError:
            pass
    try:
        decoded = base64.urlsafe_b64decode(_pad_b64(normalized))
        if len(decoded) in {16, 24, 32}:
            return decoded
    except Exception:
        pass
    if len(normalized.encode("utf-8")) >= 16:
        return hashlib.sha256(normalized.encode("utf-8")).digest()
    return None


def _key_id() -> str:
    configured = (_setting("data_encryption_key_id") or "").strip()
    if configured:
        return configured
    return hashlib.sha256(_key_bytes()).hexdigest()[:12]


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(_pad_b64(value))


def _pad_b64(value: str) -> str:
    return value + "=" * (-len(value) % 4)
