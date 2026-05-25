from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Conversation, Subtask, Task
from app.services.workflows.definition import _conversation_agents
from app.services.workflows.planning import build_plan


def create_task_for_prompt(
    db: Session, conversation: Conversation, prompt: str, plan: dict[str, Any] | None = None
) -> Task:
    agents = _conversation_agents(db, conversation)
    plan = plan or build_plan(prompt, agents)
    task = Task(
        conversation_id=conversation.id,
        creator_id=conversation.creator_id,
        title=prompt[:80] or "多 Agent 协作任务",
        description=prompt,
        status="PENDING",
        priority="high",
        progress=5,
        plan=plan,
        input={"prompt": prompt},
    )
    db.add(task)
    db.flush()
    for index, spec in enumerate(plan["subtasks"]):
        db.add(
            Subtask(
                parent_task_id=task.id,
                title=spec["title"],
                description=spec["description"],
                status="PENDING",
                order_index=index,
                agent_id=spec.get("assigned_agent_id"),
                input=spec,
            )
        )
    db.flush()
    return task


def task_plan_json(task: Task) -> str:
    return json.dumps(task.plan, ensure_ascii=False, indent=2)
