from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Conversation, User
from app.services.conversation_identity import conversation_number
from app.services.files.workspace_naming import ROOT_LABELS, duplicate_suffix, readable_segment
from app.services.files.workspace_node_types import WorkspaceFileNode
from app.services.files.workspace_sources import artifact_nodes, filesystem_nodes, project_nodes, upload_nodes


def collect_workspace_file_root(
    db: Session,
    *,
    user: User,
    workspace_id: str,
    root: Path,
    conversations: list[Conversation],
    favorites: set[str] | None = None,
) -> WorkspaceFileNode:
    builder = _TreeBuilder(workspace_id, _directory_labels(db, root, conversations), favorites or set())
    seen_paths: set[str] = set()
    for node in upload_nodes(db, user, workspace_id, root, conversations):
        builder.add(node)
        seen_paths.add(node.path)
    for node in artifact_nodes(db, workspace_id, conversations):
        builder.add(node)
    for node in project_nodes(db, workspace_id):
        builder.add(node)
    for node in filesystem_nodes(workspace_id, root, seen_paths):
        builder.add(node)
    return builder.root()


class _TreeBuilder:
    def __init__(self, workspace_id: str, directory_labels: dict[str, str], favorites: set[str]) -> None:
        self.directory_labels = directory_labels
        self.favorites = favorites
        self.nodes: dict[str, WorkspaceFileNode] = {
            "": WorkspaceFileNode(
                id=f"workspace:{workspace_id}",
                name="工作区文件",
                display_name="工作区文件",
                type="directory",
                path="",
                source="workspace",
            )
        }

    def add(self, node: WorkspaceFileNode) -> None:
        parts = [part for part in node.path.split("/") if part]
        parent_path = ""
        for index, part in enumerate(parts[:-1]):
            current_path = "/".join(parts[: index + 1])
            if current_path not in self.nodes:
                name = self._directory_name(current_path, part)
                self.nodes[current_path] = WorkspaceFileNode(
                    id=f"dir:{quote(current_path, safe='')}",
                    name=name,
                    display_name=name,
                    type="directory",
                    path=current_path,
                    source=parts[0],
                )
                self.nodes[parent_path].children.append(self.nodes[current_path])
            parent_path = current_path
        self.nodes[parent_path].children.append(node)

    def root(self) -> WorkspaceFileNode:
        self._sort(self.nodes[""])
        self._dedupe_names(self.nodes[""])
        self._assign_display_paths(self.nodes[""], [])
        self._mark_favorites(self.nodes[""])
        return self.nodes[""]

    def _directory_name(self, path: str, part: str) -> str:
        return (
            self.directory_labels.get(path)
            or ROOT_LABELS.get(path)
            or ROOT_LABELS.get(part)
            or readable_segment(part, path=path)
        )

    def _sort(self, node: WorkspaceFileNode) -> None:
        node.children.sort(key=lambda item: (item.type != "directory", item.display_name.lower()))
        for child in node.children:
            self._sort(child)

    def _dedupe_names(self, node: WorkspaceFileNode) -> None:
        buckets: dict[str, list[WorkspaceFileNode]] = {}
        for child in node.children:
            buckets.setdefault(child.display_name.lower(), []).append(child)
        for siblings in buckets.values():
            if len(siblings) > 1:
                _rename_duplicate_files(siblings)
        for child in node.children:
            self._dedupe_names(child)

    def _mark_favorites(self, node: WorkspaceFileNode) -> None:
        node.favorite = node.id in self.favorites or node.path in self.favorites
        for child in node.children:
            self._mark_favorites(child)

    def _assign_display_paths(self, node: WorkspaceFileNode, parents: list[str]) -> None:
        if node.type == "file":
            node.display_path = " / ".join(parents) if parents else node.path
            return
        next_parents = parents + ([node.display_name] if node.path else [])
        for child in node.children:
            self._assign_display_paths(child, next_parents)


def _rename_duplicate_files(siblings: list[WorkspaceFileNode]) -> None:
    for item in siblings:
        if item.type == "file":
            stem = Path(item.display_name).stem
            ext = Path(item.display_name).suffix
            item.display_name = f"{stem} ({duplicate_suffix(item.updated_at, item.id)}){ext}"


def _directory_labels(db: Session, root: Path, conversations: list[Conversation]) -> dict[str, str]:
    labels: dict[str, str] = {}
    workspace_conversations = {conversation.id: conversation for conversation in conversations}
    discovered_conversations = _path_conversations(db, root, workspace_conversations)
    user_labels = _user_labels(db, discovered_conversations)

    for area in ("uploads", "files", "sandbox", "exports", "artifacts"):
        labels[f"{area}/conversations"] = "按会话归档"
        labels[f"{area}/legacy"] = "历史文件"

    for conversation in discovered_conversations:
        conversation_label = _conversation_label(conversation)
        for area in ("uploads", "files", "sandbox", "exports", "artifacts"):
            prefix = f"{area}/conversations/{conversation.id}"
            labels[prefix] = conversation_label
            labels[f"{area}/legacy/{conversation.id}"] = conversation_label
            labels[f"{prefix}/agents"] = "Agent 输出"
            labels[f"{prefix}/tasks"] = "任务输出"
            if conversation.creator_id:
                labels[f"{prefix}/{conversation.creator_id}"] = (
                    user_labels.get(conversation.creator_id)
                    or f"用户：{conversation.creator_id[:8]}"
                )
            for participant in conversation.participants:
                if not participant.agent_id:
                    continue
                agent_name = participant.agent.name if participant.agent else participant.agent_id[:8]
                labels[f"{prefix}/agents/{participant.agent_id}"] = f"Agent：{agent_name}"

    conversation_ids = {item.id for item in conversations}
    artifacts = db.scalars(
        select(Artifact).where(
            Artifact.conversation_id.in_(conversation_ids),
            Artifact.deleted_at.is_(None),
        )
    ).all()
    for artifact in artifacts:
        label = _artifact_label(artifact)
        labels[f"artifacts/{artifact.id}"] = label
        if artifact.conversation_id:
            labels[f"artifacts/conversations/{artifact.conversation_id}/{artifact.id}"] = label
    return labels


def _conversation_label(conversation: Conversation) -> str:
    kind = "群聊" if conversation.chat_type == "group" else "单聊"
    return f"{kind}：{conversation.title or '会话'} · {conversation_number(conversation)}"


def _artifact_label(artifact: Artifact) -> str:
    content = artifact.content if isinstance(artifact.content, dict) else {}
    filename = str(content.get("filename") or "").strip()
    fallback = Path(filename).stem if filename else ""
    name = str(artifact.name or fallback or "未命名产物").strip()
    return f"产物：{name} · {artifact.id[:8]}"


def _user_labels(db: Session, conversations: list[Conversation]) -> dict[str, str]:
    user_ids = {conversation.creator_id for conversation in conversations if conversation.creator_id}
    users = db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    labels: dict[str, str] = {}
    for user in users:
        name = user.display_name or user.username or user.email or "用户"
        labels[user.id] = f"用户：{name} · {user.id[:8]}"
    return labels


def _path_conversations(db: Session, root: Path, conversations: dict[str, Conversation]) -> list[Conversation]:
    ids = set(conversations)
    for path in root.rglob("*"):
        for part in path.parts:
            if len(part) == 36 and part.count("-") == 4:
                ids.add(part)
    found = db.scalars(select(Conversation).where(Conversation.id.in_(ids))).all() if ids else []
    merged = {item.id: item for item in found}
    merged.update(conversations)
    return list(merged.values())
