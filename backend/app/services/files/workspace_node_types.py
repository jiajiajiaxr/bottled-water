from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkspaceFileNode:
    id: str
    name: str
    display_name: str
    type: str
    path: str
    source: str
    size: int = 0
    display_path: str | None = None
    updated_at: str | None = None
    mime_type: str | None = None
    download_url: str | None = None
    preview_url: str | None = None
    favorite: bool = False
    children: list["WorkspaceFileNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "type": self.type,
            "path": self.path,
            "display_path": self.display_path,
            "size": self.size,
            "updated_at": self.updated_at,
            "source": self.source,
            "mime_type": self.mime_type,
            "download_url": self.download_url,
            "preview_url": self.preview_url,
            "favorite": self.favorite,
            "children": [child.to_dict() for child in self.children],
        }
