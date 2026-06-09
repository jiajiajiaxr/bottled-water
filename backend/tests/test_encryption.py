from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.services.tools.builtins.artifact.export import export_artifact
from app.services.tools.executor import invoke_tool
from common.crypto import BYTES_PREFIX, read_encrypted_file
from db.base import Base
from db.session import AsyncSessionLocal
from db.models import Artifact, Conversation, Message, ModelProvider, User


def unwrap(body: dict[str, Any]) -> Any:
    return body.get("data", body)


def memory_session() -> Any:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_new_message_content_is_encrypted_at_rest_and_decrypted_by_orm() -> None:
    db = memory_session()
    user = User(email="encryption-msg@example.com", username="enc-msg", password_hash="x")
    db.add(user)
    db.flush()
    conversation = Conversation(creator_id=user.id, chat_type="single", title="encrypted messages")
    db.add(conversation)
    db.flush()
    message = Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name="User",
        content_type="text",
        content={"text": "sensitive chat body", "message_id": "stream-1"},
    )
    db.add(message)
    db.commit()

    raw = db.execute(text("select content from messages where id = :id"), {"id": message.id}).scalar_one()

    assert "sensitive chat body" not in raw
    assert "enc:v1:" in raw
    assert "stream-1" in raw
    assert db.get(Message, message.id).content["text"] == "sensitive chat body"


def test_new_model_provider_secret_is_encrypted_at_rest_and_decrypted_by_orm() -> None:
    db = memory_session()
    user = User(email="encryption-model@example.com", username="enc-model", password_hash="x")
    provider = ModelProvider(
        owner_id=user.id,
        name="Encrypted Provider",
        provider_type="openai-compatible",
        base_url="https://example.test/v1",
        api_key_ref="sk-test-secret",
        default_model="demo",
    )
    db.add_all([user, provider])
    db.commit()

    raw = db.execute(
        text("select api_key_ref from model_providers where id = :id"),
        {"id": provider.id},
    ).scalar_one()

    assert raw.startswith("enc:v1:")
    assert "sk-test-secret" not in raw
    assert db.get(ModelProvider, provider.id).api_key_ref == "sk-test-secret"


async def _file_asset_storage_path(file_id: str) -> Path:
    async with AsyncSessionLocal() as db:
        row = await db.execute(text("select storage_path from file_assets where id = :id"), {"id": file_id})
        return Path(row.scalar_one())


def test_new_uploaded_file_is_encrypted_on_disk_but_downloads_plaintext(
    client: Any,
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    raw = b"Plain text recognition works with encrypted storage."
    uploaded = client.post(
        "/api/v1/files/upload",
        data={"conversation_id": conversation_id},
        files={"file": ("encrypted-notes.txt", io.BytesIO(raw), "text/plain")},
        headers=auth_headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    asset = unwrap(uploaded.json())
    stored_path = anyio.run(_file_asset_storage_path, asset["id"])

    assert stored_path.read_bytes().startswith(BYTES_PREFIX)
    assert raw not in stored_path.read_bytes()

    downloaded = client.get(f"/api/v1/files/{asset['id']}/download", headers=auth_headers)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == raw


def test_new_artifact_source_file_is_encrypted_on_disk_and_exports_plaintext() -> None:
    db = memory_session()
    user = User(email="encryption-artifact@example.com", username="enc-artifact", password_hash="x")
    db.add(user)
    db.flush()
    conversation = Conversation(creator_id=user.id, chat_type="single", title="encrypted artifacts")
    db.add(conversation)
    db.commit()

    result = invoke_tool(
        db,
        user,
        "artifact.create_html",
        {
            "conversation_id": conversation.id,
            "title": "Encrypted HTML",
            "html": "<!doctype html><html><body>artifact plaintext</body></html>",
        },
    )
    artifact = db.scalar(select(Artifact).where(Artifact.id == result["result"]["artifact_id"]))
    exported = export_artifact(artifact, "html")
    stored_path = Path(artifact.content["source_file"]["storage_path"])

    assert stored_path.read_bytes().startswith(BYTES_PREFIX)
    assert exported.content == b"<!doctype html><html><body>artifact plaintext</body></html>"
    assert read_encrypted_file(stored_path) == exported.content
