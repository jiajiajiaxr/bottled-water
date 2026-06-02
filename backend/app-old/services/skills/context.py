from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, Skill
from app.services.skills.adapters.legacy import legacy_skill_manifest


def activated_skill_context(db: Session, agent: Agent, *, max_chars: int = 3000) -> str:
    """渲染 Agent 已授权 Skill 包摘要，用于注入模型上下文。"""

    skill_ids = [str(item) for item in (agent.config or {}).get("skill_ids") or [] if item]
    if not skill_ids:
        return ""
    skills = db.scalars(
        select(Skill).where(Skill.id.in_(skill_ids), Skill.deleted_at.is_(None), Skill.status == "active")
    ).all()
    if not skills:
        return ""
    blocks = ["\n已激活的 Skill 包："]
    for skill in skills:
        manifest = legacy_skill_manifest(skill)
        entry = manifest.get("entry") if isinstance(manifest.get("entry"), dict) else {}
        prompt = str(entry.get("prompt") or "")[:700]
        dependencies = manifest.get("dependencies") or {}
        blocks.append(
            "\n".join(
                [
                    f"- {manifest['name']} v{manifest['version']} ({manifest['runtime']})",
                    f"  描述：{manifest.get('description') or skill.description or '无'}",
                    f"  依赖：tools={dependencies.get('tools', [])}, mcp={dependencies.get('mcp_servers', [])}",
                    f"  使用指南：{prompt}",
                    f"  如需显式运行，调用 function `skill.{skill.id}`。",
                ]
            )
        )
    text = "\n".join(blocks)
    return text[:max_chars]
