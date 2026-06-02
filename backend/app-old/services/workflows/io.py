from __future__ import annotations

import json
from typing import Any

from app.services.context.variables import artifact_reference_scope
from app.services.context.variables import lookup as _lookup_reference
from app.services.context.variables import resolve_value
from app.services.context.variables import stringify as _stringify_reference
from app.services.workflows.graph import Node, WorkflowGraph


def collect_upstream_outputs(
    graph: WorkflowGraph,
    node: Node,
    outputs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """按入边收集当前节点的上游输出。"""
    return {edge.source: outputs.get(edge.source, {}) for edge in graph.incoming.get(node.id, [])}


def summarize_outputs(outputs: dict[str, dict[str, Any]]) -> str:
    """提取节点输出中的可读文本，供 {{upstream.text}} 使用。"""
    parts: list[str] = []
    for node_id, output in outputs.items():
        text = _first_text(output)
        if text:
            parts.append(f"{node_id}: {text}")
    return "\n".join(parts)


def resolve_node_input(
    *,
    node: Node,
    graph: WorkflowGraph,
    prompt: str,
    outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """解析节点输入，形成统一数据流上下文。"""
    upstream = collect_upstream_outputs(graph, node, outputs)
    scope = build_reference_scope(prompt=prompt, outputs=outputs, upstream=upstream, node=node)
    configured_input = node.config.get("input", node.config.get("inputs"))
    mapped = resolve_value(configured_input, scope) if configured_input is not None else {}
    node_input = {
        "input": prompt,
        "prompt": prompt,
        "nodes": outputs,
        "upstream": upstream,
        "upstream_text": summarize_outputs(upstream),
        "mapped": mapped if mapped is not None else {},
    }
    if isinstance(mapped, dict):
        node_input.update(mapped)
    elif mapped not in (None, ""):
        node_input["value"] = mapped
        node_input.setdefault("text", str(mapped))
    return node_input


def resolve_node_output(
    *,
    node: Node,
    prompt: str,
    outputs: dict[str, dict[str, Any]],
    node_input: dict[str, Any],
    raw_output: dict[str, Any],
    graph: WorkflowGraph,
) -> dict[str, Any]:
    """根据 config.output 映射生成标准节点输出。"""
    configured_output = node.config.get("output", node.config.get("outputs"))
    if configured_output is None:
        return raw_output
    upstream = collect_upstream_outputs(graph, node, outputs)
    scope = build_reference_scope(
        prompt=prompt,
        outputs=outputs,
        upstream=upstream,
        node=node,
        node_input=node_input,
        raw_output=raw_output,
    )
    mapped = resolve_value(configured_output, scope)
    if isinstance(mapped, dict):
        return mapped
    if isinstance(mapped, list):
        return {"items": mapped}
    return {"text": "" if mapped is None else str(mapped)}


def build_reference_scope(
    *,
    prompt: str,
    outputs: dict[str, dict[str, Any]],
    upstream: dict[str, dict[str, Any]],
    node: Node,
    node_input: dict[str, Any] | None = None,
    raw_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建模板变量解析作用域。"""
    scope: dict[str, Any] = {
        "input": prompt,
        "prompt": prompt,
        "nodes": outputs,
        "upstream": {"nodes": upstream, "text": summarize_outputs(upstream)},
        "artifact": artifact_reference_scope(_artifacts_from_outputs(outputs)),
        "artifacts": artifact_reference_scope(_artifacts_from_outputs(outputs)),
        "node": {"id": node.id, "title": node.title, "type": node.type, "config": node.config},
    }
    if node_input is not None:
        scope["node_input"] = node_input
        scope["current"] = node_input
    if raw_output is not None:
        scope["output"] = raw_output
        scope["result"] = raw_output
    return scope


def format_node_input_for_agent(node: Node, node_input: dict[str, Any]) -> str:
    """把节点输入整理成适合放入模型上下文的说明。"""
    mapped = node_input.get("mapped")
    mapped_text = _json_text(mapped) if mapped not in ({}, None, "") else "无"
    upstream_text = str(node_input.get("upstream_text") or "无")
    return (
        f"用户原始消息：\n{node_input.get('input', '')}\n\n"
        f"当前工作流节点：{node.title}\n{node.meta}\n\n"
        f"上游节点输出：\n{upstream_text}\n\n"
        f"当前节点输入映射：\n{mapped_text}"
    )


def input_mapping_as_arguments(node_input: dict[str, Any]) -> dict[str, Any]:
    """将节点 input 映射转换为工具参数。"""
    mapped = node_input.get("mapped")
    if isinstance(mapped, dict):
        return dict(mapped)
    if mapped not in (None, ""):
        return {"value": mapped, "prompt": str(mapped)}
    return {}


def resolve_references(value: Any, outputs: dict[str, dict[str, Any]]) -> Any:
    """兼容旧调用：只提供 nodes 作用域的模板解析。"""
    return resolve_value(value, {"nodes": outputs, **outputs})


def _lookup(scope: dict[str, Any], expr: str) -> Any:
    return _lookup_reference(scope, expr)


def _stringify(value: Any) -> str:
    return _stringify_reference(value)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _first_text(output: dict[str, Any]) -> str:
    for key in ("text", "summary", "content", "output"):
        value = output.get(key)
        if value:
            return _stringify(value)[:1000]
    result = output.get("result")
    if isinstance(result, dict):
        return _first_text(result)
    return _stringify(result)[:1000] if result else ""


def _artifacts_from_outputs(outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for node_id, output in outputs.items():
        artifact_id = output.get("artifact_id") or output.get("id")
        if artifact_id or output.get("preview_url") or output.get("export_url"):
            artifacts.append({"node_id": node_id, **output})
    return artifacts
