from __future__ import annotations

import re


_INTERNAL_SECTION_TITLES = {"任务拆解", "执行过程", "合规审查"}
_FINAL_SECTION_TITLES = {
    "最终产物",
    "最终回答",
    "最终回复",
    "最终结果",
    "正式回复",
    "回复",
}
_STATUS_REPORT_FENCE = "```status_report"
_STATUS_REPORT_NAMES = ("status_report", "status")
_STATUS_REPORT_FENCE_RE = re.compile(r"^```\s*(?:status_report|status)\b", re.IGNORECASE)


def _can_become_status_report_fence(value: str) -> bool:
    """Return True for an in-flight fence prefix that should stay hidden."""
    if not value:
        return False
    normalized = value.strip().lower()
    if _STATUS_REPORT_FENCE.startswith(normalized):
        return True
    if re.match(r"^```\s*(?:status_report|status)\b", normalized, flags=re.IGNORECASE):
        return True
    partial = re.match(r"^```\s*([a-z_]*)$", normalized, flags=re.IGNORECASE)
    return bool(
        partial
        and any(name.startswith(partial.group(1).lower()) for name in _STATUS_REPORT_NAMES)
    )


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

    raw, removed_fence = _strip_internal_fenced_blocks(raw)
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
    return cleaned if cleaned or not (saw_internal or removed_fence) else ""


class InternalOutputStreamFilter:
    """Incrementally expose only user-facing text from a streaming model response."""

    def __init__(self) -> None:
        self._raw = ""
        self._visible = ""

    def push(self, delta: str) -> str:
        """Append a raw model delta and return only newly visible text."""
        if not delta:
            return ""
        self._raw += delta
        visible = strip_internal_agent_output(self._raw)
        if not visible:
            self._visible = ""
            return ""
        if visible.startswith(self._visible):
            new_text = visible[len(self._visible) :]
        else:
            # If filtering removed a previously visible tail, avoid emitting a duplicate rewrite.
            new_text = ""
        self._visible = visible
        return new_text

    @property
    def visible_text(self) -> str:
        return self._visible


def _strip_internal_fenced_blocks(text: str) -> tuple[str, bool]:
    """Remove complete or currently streaming status_report fenced code blocks."""
    lines = text.splitlines()
    visible: list[str] = []
    skipping = False
    removed = False

    for index, line in enumerate(lines):
        trimmed = line.strip()
        lowered = trimmed.lower()

        if skipping:
            if lowered.startswith("```"):
                skipping = False
            continue

        if _STATUS_REPORT_FENCE_RE.match(trimmed):
            skipping = True
            removed = True
            continue

        if index == len(lines) - 1 and _can_become_status_report_fence(lowered):
            removed = True
            continue

        if lowered == "```" and index == len(lines) - 1:
            removed = True
            continue

        if (
            lowered.startswith("```")
            and lowered != "```"
            and _STATUS_REPORT_FENCE.startswith(lowered)
        ):
            skipping = True
            removed = True
            continue

        visible.append(line)

    return "\n".join(visible), removed
