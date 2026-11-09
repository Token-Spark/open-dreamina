# Copyright 2026 Open Dreamina Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""画布文档校验：分「结构校验」与「业务校验」两层，前后端共用同一份规则。

- ``validate_structure``：只拦截会导致读取 / 渲染崩溃的畸形输入，是**唯一**
  允许阻断保存的校验层。画布是编辑器，用户正在搭建、尚未填完的工作图
  必须能落库，否则自动保存会持续失败并把编辑内容困在内存里。
- ``validate_document``：完整的业务规则（图是否可执行、端口是否合法、
  节点是否配置齐全等）。结果作为 ``issues`` 提示用户，**不阻断保存**；
  将来画布执行编排时，才应据此拦截运行。

两层都是无 DB 依赖的纯函数。``validate_document`` 允许输入存在轻微畸形，
逐项跳过而不是抛异常，以便对历史文档也能安全地给出提示。
"""
from __future__ import annotations

import math
from typing import Any

from .canvas_graph import detect_cycle, edges_to_port
from .canvas_specs import (
    GENERATION_NODE_TYPES,
    NODE_SPECS,
    get_port_spec,
    is_port_type_compatible,
)


def _issue(
    level: str,
    code: str,
    message: str,
    node_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
    fix: str = "",
) -> dict[str, Any]:
    """构造统一的校验条目。"""
    return {
        "level": level,
        "code": code,
        "message": message,
        "node_ids": node_ids or [],
        "edge_ids": edge_ids or [],
        "fix": fix,
    }


def _safe_parts(doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """提取结构可用的节点 / 边 / 索引，跳过畸形项。

    返回给业务校验用的边是副本，``order`` 已归一为数字，避免排序时抛异常。
    """
    raw_nodes = doc.get("nodes", [])
    raw_edges = doc.get("edges", [])
    nodes: list[dict[str, Any]] = []
    if isinstance(raw_nodes, list):
        nodes = [
            n for n in raw_nodes
            if isinstance(n, dict) and isinstance(n.get("id"), str) and n["id"]
        ]
    node_map = {n["id"]: n for n in nodes}

    graph_edges: list[dict[str, Any]] = []
    if isinstance(raw_edges, list):
        for edge in raw_edges:
            if not isinstance(edge, dict):
                continue
            if not isinstance(edge.get("source"), str) or not isinstance(edge.get("target"), str):
                continue
            item = dict(edge)
            order = item.get("order", 0)
            if isinstance(order, bool) or not isinstance(order, (int, float)):
                item["order"] = 0
            graph_edges.append(item)
    return nodes, graph_edges, node_map


def validate_structure(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """保存前的结构校验：只拦截会让文档无法读取 / 渲染的畸形输入。

    通过校验的文档保证：nodes / edges 是列表，节点有唯一 id、已知类型、
    dict 型 data、数值型坐标，边有唯一 id、合法端口名、指向存在的节点。
    业务上是否「可执行」不在本层判断。
    """
    results: list[dict[str, Any]] = []

    raw_nodes = doc.get("nodes", [])
    raw_edges = doc.get("edges", [])
    if not isinstance(raw_nodes, list):
        return [_issue("error", "invalid_nodes", "nodes 必须是数组", fix="修正文档结构后重试")]
    if not isinstance(raw_edges, list):
        return [_issue("error", "invalid_edges", "edges 必须是数组", fix="修正文档结构后重试")]

    viewport = doc.get("viewport")
    if viewport is not None and not isinstance(viewport, dict):
        results.append(_issue("error", "invalid_viewport", "viewport 必须是对象"))

    node_ids: set[str] = set()
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            results.append(_issue("error", "invalid_node", f"第 {index + 1} 个节点不是对象"))
            continue
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            results.append(_issue("error", "invalid_node_id", f"第 {index + 1} 个节点缺少有效 id"))
            continue
        if nid in node_ids:
            results.append(_issue("error", "duplicate_node_id", f"节点 id 重复: {nid}", node_ids=[nid]))
            continue
        node_ids.add(nid)

        ntype = node.get("type")
        if not isinstance(ntype, str) or ntype not in NODE_SPECS:
            results.append(_issue("error", "unknown_node_type", f"节点 {nid} 类型未知: {ntype}",
                                  node_ids=[nid], fix=f"使用已知类型: {list(NODE_SPECS.keys())}"))
        if "data" in node and not isinstance(node.get("data"), dict):
            results.append(_issue("error", "invalid_node_data", f"节点 {nid} 的 data 必须是对象", node_ids=[nid]))
        position = node.get("position")
        if position is not None:
            if not isinstance(position, dict):
                results.append(_issue("error", "invalid_node_position", f"节点 {nid} 的 position 必须是对象", node_ids=[nid]))
            else:
                x, y = position.get("x"), position.get("y")
                if (isinstance(x, bool) or isinstance(y, bool)
                        or not isinstance(x, (int, float)) or not isinstance(y, (int, float))
                        or not math.isfinite(x) or not math.isfinite(y)):
                    results.append(_issue("error", "invalid_node_position",
                                          f"节点 {nid} 的 position.x / y 必须是有限数值", node_ids=[nid]))

    edge_ids: set[str] = set()
    for index, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            results.append(_issue("error", "invalid_edge", f"第 {index + 1} 条边不是对象"))
            continue
        eid = edge.get("id")
        if not isinstance(eid, str) or not eid:
            results.append(_issue("error", "invalid_edge_id", f"第 {index + 1} 条边缺少有效 id"))
            continue
        if eid in edge_ids:
            results.append(_issue("error", "duplicate_edge_id", f"边 id 重复: {eid}", edge_ids=[eid]))
            continue
        edge_ids.add(eid)

        src, tgt = edge.get("source"), edge.get("target")
        if not isinstance(src, str) or not src or src not in node_ids:
            results.append(_issue("error", "dangling_edge", f"边 {eid} 的 source 无效或指向不存在的节点", edge_ids=[eid]))
        if not isinstance(tgt, str) or not tgt or tgt not in node_ids:
            results.append(_issue("error", "dangling_edge", f"边 {eid} 的 target 无效或指向不存在的节点", edge_ids=[eid]))
        if not isinstance(edge.get("source_port", ""), str) or not isinstance(edge.get("target_port", ""), str):
            results.append(_issue("error", "invalid_edge_port", f"边 {eid} 的端口名必须是字符串", edge_ids=[eid]))
        # 允许数值即可（排序只需要可比较）；历史文档里可能有浮点 order，
        # 不必为此拒绝一整份草稿。
        order = edge.get("order", 0)
        if isinstance(order, bool) or not isinstance(order, (int, float)):
            results.append(_issue("error", "invalid_edge_order", f"边 {eid} 的 order 必须是数值", edge_ids=[eid]))

    return results


def validate_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """业务校验：返回 errors + warnings，用于生成「待完善项」提示。

    每条: {level, code, message, node_ids, edge_ids, fix}
    调用方（保存/执行）自行决定如何处理；本函数不抛异常、不阻断写入。
    """
    results: list[dict[str, Any]] = []
    nodes, edges, node_map = _safe_parts(doc)
    safe_doc = {"nodes": nodes, "edges": edges}

    # 1. 环检测
    cycle_nodes = detect_cycle(safe_doc)
    if cycle_nodes:
        results.append(_issue("error", "cycle_detected", f"节点 {', '.join(cycle_nodes)} 构成环",
                              node_ids=cycle_nodes, fix="删除构成环的边"))

    # 2. 逐节点校验
    for node in nodes:
        nid = node["id"]
        ntype = node.get("type", "")
        if not isinstance(ntype, str):
            ntype = ""
        if ntype not in NODE_SPECS:
            results.append(_issue("error", "unknown_node_type", f"节点 {nid} 类型未知: {ntype}",
                                  node_ids=[nid], fix=f"使用已知类型: {list(NODE_SPECS.keys())}"))
            continue

        data = node.get("data", {})
        if not isinstance(data, dict):
            data = {}

        # 2a. 生成节点缺 provider / model
        if ntype in GENERATION_NODE_TYPES:
            if not data.get("provider"):
                results.append(_issue("error", "missing_provider", f"节点 {nid} 缺少 provider",
                                      node_ids=[nid], fix="在节点内选择 provider"))
            if not data.get("model_id"):
                results.append(_issue("error", "missing_model", f"节点 {nid} 缺少 model_id",
                                      node_ids=[nid], fix="在节点内选择模型"))

            # 2b. 生成节点无提示词且无 prompt 入边
            prompt_edges = edges_to_port(safe_doc, nid, "prompt")
            has_local_prompt = bool(str(data.get("prompt") or "").strip())
            if not prompt_edges and not has_local_prompt:
                results.append(_issue("error", "missing_prompt", f"节点 {nid} 无提示词且无 prompt 入边",
                                      node_ids=[nid], fix="填写提示词，或连一条 prompt 节点的入边"))

    # 3. 逐边校验（端口存在性与类型兼容）
    for edge in edges:
        eid = edge.get("id", "")
        src_id, tgt_id = edge.get("source"), edge.get("target")
        src_port = edge.get("source_port", "")
        tgt_port = edge.get("target_port", "")
        if not isinstance(src_port, str):
            src_port = ""
        if not isinstance(tgt_port, str):
            tgt_port = ""

        src_node = node_map.get(src_id)
        tgt_node = node_map.get(tgt_id)
        if not src_node or not tgt_node:
            results.append(_issue("error", "dangling_edge", f"边 {eid} 引用了不存在的节点",
                                  node_ids=[s for s in (src_id, tgt_id) if isinstance(s, str)],
                                  edge_ids=[eid], fix="删除这条边"))
            continue

        src_type = src_node.get("type", "")
        tgt_type = tgt_node.get("type", "")
        out_spec = get_port_spec(src_type, src_port, "outputs") if isinstance(src_type, str) else None
        in_spec = get_port_spec(tgt_type, tgt_port, "inputs") if isinstance(tgt_type, str) else None
        if not out_spec or not in_spec:
            results.append(_issue("error", "invalid_port",
                                  f"边 {eid} 的端口不存在 ({src_id}.{src_port} -> {tgt_id}.{tgt_port})",
                                  node_ids=[src_id, tgt_id], edge_ids=[eid], fix="检查节点规格，删除或重新连接"))
            continue

        if not is_port_type_compatible(out_spec["types"], in_spec["types"]):
            results.append(_issue("error", "type_mismatch",
                                  f"边 {eid} 类型不匹配: {out_spec['types']} -> {in_spec['types']}",
                                  node_ids=[src_id, tgt_id], edge_ids=[eid], fix="连接类型兼容的端口"))
            continue

    # 4. 端口容量（按目标端口聚合，每个端口只报一次）
    port_edges: dict[tuple[str, str], list[str]] = {}
    for edge in edges:
        tgt_id, tgt_port = edge.get("target"), edge.get("target_port", "")
        if not isinstance(tgt_id, str) or not isinstance(tgt_port, str):
            continue
        port_edges.setdefault((tgt_id, tgt_port), []).append(edge.get("id", ""))
    for (tgt_id, tgt_port), ids in port_edges.items():
        tgt_node = node_map.get(tgt_id)
        tgt_type = tgt_node.get("type", "") if tgt_node else ""
        in_spec = get_port_spec(tgt_type, tgt_port, "inputs") if isinstance(tgt_type, str) else None
        if not in_spec:
            continue
        if not in_spec.get("multi") and len(ids) > 1:
            results.append(_issue("error", "port_capacity_exceeded", f"端口 {tgt_id}.{tgt_port} 不支持多条入边",
                                  node_ids=[tgt_id], edge_ids=ids, fix="删除多余的入边"))
        max_count = in_spec.get("max")
        if max_count and len(ids) > max_count:
            results.append(_issue("error", "port_capacity_exceeded",
                                  f"端口 {tgt_id}.{tgt_port} 超出上限 {max_count}（当前 {len(ids)}）",
                                  node_ids=[tgt_id], edge_ids=ids, fix=f"删除入边，保留不超过 {max_count} 条"))

    # 5. 节点数警告
    if len(nodes) > 80:
        results.append(_issue("warning", "too_many_nodes",
                              f"画布有 {len(nodes)} 个节点，建议拆分以避免性能下降",
                              fix="将画布拆分为多个子画布"))

    # 6. 孤立生成节点警告
    for node in nodes:
        if node.get("type") not in GENERATION_NODE_TYPES:
            continue
        has_downstream = any(e.get("source") == node["id"] for e in edges)
        if not has_downstream:
            results.append(_issue("warning", "orphan_generation_node",
                                  f"生成节点 {node['id']} 没有下游节点，产物不会被继续引用",
                                  node_ids=[node["id"]], fix="将结果连到下游节点以继续编排"))

    return results


def split_errors(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """将校验结果拆分为 errors 与 warnings。"""
    errors = [i for i in items if i["level"] == "error"]
    warnings = [i for i in items if i["level"] == "warning"]
    return errors, warnings
