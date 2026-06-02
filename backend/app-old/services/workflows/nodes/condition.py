from __future__ import annotations

import re

from app.services.workflows.graph import Node
from app.services.workflows.io import resolve_value
from app.services.workflows.nodes.base import (
    NodeExecutionResult,
    WorkflowExecutionContext,
    WorkflowNodeExecutor,
)


class ConditionNodeExecutor(WorkflowNodeExecutor):
    node_type = "condition"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        node_input = getattr(context, "node_input", {}) or {}
        raw_expression = node_input.get("expression") or node.config.get("expression") or "true"
        expression = str(resolve_value(raw_expression, _scope(context, node_input))).strip()
        branches = (
            node.config.get("branches")
            if isinstance(node.config.get("branches"), list)
            else ["true", "false"]
        )
        matched = str(branches[0] if branches else "true")
        source_text = "\n".join(
            [
                str(node_input.get("input") or context.prompt),
                str(node_input.get("upstream_text") or ""),
                str(node_input.get("text") or node_input.get("query") or ""),
            ]
        )
        if expression.lower() in {"false", "no", "0"}:
            matched = str(branches[1] if len(branches) > 1 else "false")
        elif expression.lower() not in {"true", "yes", "1"}:
            match = re.search(r"contains\\((?P<value>.+)\\)", expression)
            if match:
                needle = match.group("value").strip("'\" ")
                matched = str(
                    branches[0]
                    if needle in source_text
                    else (branches[1] if len(branches) > 1 else "false")
                )
        return NodeExecutionResult(
            output={
                "expression": expression,
                "matched_branch": matched,
                "input_text": source_text,
            },
            branch=matched,
            message=f"Condition matched {matched}",
        )


def _scope(context: WorkflowExecutionContext, node_input: dict) -> dict:
    return {
        "input": context.prompt,
        "nodes": context.outputs,
        "upstream": {
            "nodes": node_input.get("upstream", {}),
            "text": node_input.get("upstream_text", ""),
        },
    }
