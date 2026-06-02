from __future__ import annotations

import re


_INTERNAL_SECTION_TITLES = {"任务拆解", "执行过程", "合规审查"}
_FINAL_SECTION_TITLES = {"最终产物", "最终回答", "最终回复", "最终结果", "正式回复", "回复"}


def _section_title(line: str) -> tuple[str | None, str]:
    clean = re.sub(r"^\s*(?:#{1,6}\s*)?(?:\d+[.、)]\s*)?", "", line).strip()
    clean = clean.strip("* ")
    if not clean:
        return None, ""
    title = clean
    remainder = ""
    for sep in ("：", ":"):
        if sep in clean:
            title, remainder = clean.split(sep, 1)
            break
    title = title.strip().strip("* ")
    return title or None, remainder.strip()


def strip_internal_agent_output(text: str) -> str:
    """Keep only the user-facing answer when a model emits internal planning sections."""
    raw = str(text or "")
    if not raw.strip():
        return ""

    lines = raw.splitlines()
    for index, line in enumerate(lines):
        title, inline_remainder = _section_title(line)
        if title in _FINAL_SECTION_TITLES:
            tail = ([inline_remainder] if inline_remainder else []) + lines[index + 1 :]
            return "\n".join(tail).strip()

    visible: list[str] = []
    skipping = False
    saw_internal = False
    for line in lines:
        title, _ = _section_title(line)
        if title in _INTERNAL_SECTION_TITLES:
            saw_internal = True
            skipping = True
            continue
        if title and title not in _INTERNAL_SECTION_TITLES:
            skipping = False
        if not skipping:
            visible.append(line)
    cleaned = "\n".join(visible).strip()
    return cleaned if cleaned or not saw_internal else ""
