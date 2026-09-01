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

"""画布文档校验：规则表驱动，前后端共用同一份规则。

校验在保存前与运行前都执行，保证库中文档永远结构合法。
"""
from __future__ import annotations

from typing import Any

from .canvas_graph import detect_cycle, edges_to_port, _find_node
from .canvas_specs import (
    GENERATION_NODE_TYPES,
    NODE_SPECS,
    get_port_spec,
    is_port_type_compatible,
)


def validate_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """校验画布文档，返回 errors + warnings 列表。

    每条: {level, code, message, node_ids, edge_ids, fix}
    """
    results: list[dict[str, Any]] = []

    nodes = doc.get("nodes", [])
    edges = doc.get("edges", [])
    node_map = {n["id"]: n for n in nodes}

    # 1. 环检测
    cycle_nodes = detect_cycle(doc)
    if cycle_nodes:
        results.append({
            "level": "error",
            "code": "cycle_detected",
            "message": f"节点 {', '.join(cycle_nodes)} 构成环",
            "node_ids": cycle_nodes,
            "edge_ids": [],
            "fix": "删除构成环的边",
        })

    # 2. 逐节点校验
    for node in nodes:
        nid = node["id"]
        ntype = node.get("type", "")

        # 2a. 未知节点类型
        if ntype not in NODE_SPECS:
            results.append({
                "level": "error",
                "code": "unknown_node_type",
                "message": f"节点 {nid} 类型未知: {ntype}",
                "node_ids": [nid],
                "edge_ids": [],
                "fix": f"使用已知类型: {list(NODE_SPECS.keys())}",
            })
            continue

        # 2b. 生成节点缺 provider/model
        if ntype in GENERATION_NODE_TYPES:
            data = node.get("data", {})
            if not data.get("provider"):
                results.append({
                    "level": "error",
                    "code": "missing_provider",
                    "message": f"节点 {nid} 缺少 provider",
                    "node_ids": [nid],
                    "edge_ids": [],
                    "fix": "在右侧面板选择 provider",
                })
            if not data.get("model_id"):
                results.append({
                    "level": "error",
                    "code": "missing_model",
                    "message": f"节点 {nid} 缺少 model_id",
                    "node_ids": [nid],
                    "edge_ids": [],
                    "fix": "在右侧面板选择模型",
                })

        # 2c. 生成节点无提示词且无 prompt 入边
        if ntype in GENERATION_NODE_TYPES:
            prompt_edges = edges_to_port(doc, nid, "prompt")
            has_local_prompt = bool(node.get("data", {}).get("prompt", "").strip())
            if not prompt_edges and not has_local_prompt:
                results.append({
                    "level": "error",
                    "code": "missing_prompt",
                    "message": f"节点 {nid} 无提示词且无 prompt 入边",
                    "node_ids": [nid],
                    "edge_ids": [],
                    "fix": "在右侧面板填写提示词，或连一条 prompt 节点的入边",
                })

    # 3. 逐边校验
    for edge in edges:
        eid = edge.get("id", "")
        src_id = edge.get("source")
        tgt_id = edge.get("target")
        src_port = edge.get("source_port", "")
        tgt_port = edge.get("target_port", "")

        src_node = node_map.get(src_id)
        tgt_node = node_map.get(tgt_id)

        if not src_node or not tgt_node:
            results.append({
                "level": "error",
                "code": "dangling_edge",
                "message": f"边 {eid} 引用了不存在的节点",
                "node_ids": [s for s in [src_id, tgt_id] if s],
                "edge_ids": [eid],
                "fix": "删除这条边",
            })
            continue

        # 3a. 端口类型兼容性
        out_spec = get_port_spec(src_node["type"], src_port, "outputs")
        in_spec = get_port_spec(tgt_node["type"], tgt_port, "inputs")
        if not out_spec or not in_spec:
            results.append({
                "level": "error",
                "code": "invalid_port",
                "message": f"边 {eid} 的端口不存在 ({src_id}.{src_port} -> {tgt_id}.{tgt_port})",
                "node_ids": [src_id, tgt_id],
                "edge_ids": [eid],
                "fix": "检查节点规格，删除或重新连接",
            })
            continue

        if not is_port_type_compatible(out_spec["types"], in_spec["types"]):
            results.append({
                "level": "error",
                "code": "type_mismatch",
                "message": f"边 {eid} 类型不匹配: {out_spec['types']} -> {in_spec['types']}",
                "node_ids": [src_id, tgt_id],
                "edge_ids": [eid],
                "fix": "连接类型兼容的端口",
            })

        # 3b. 非 multi 端口至多一条入边
        if not in_spec.get("multi"):
            existing = edges_to_port(doc, tgt_id, tgt_port)
            if len(existing) > 1:
                results.append({
                    "level": "error",
                    "code": "port_capacity_exceeded",
                    "message": f"端口 {tgt_id}.{tgt_port} 不支持多条入边",
                    "node_ids": [tgt_id],
                    "edge_ids": [e.get("id", "") for e in existing],
                    "fix": "删除多余的入边",
                })

        # 3c. multi 端口不超过 max
        max_count = in_spec.get("max")
        if max_count:
            existing = edges_to_port(doc, tgt_id, tgt_port)
            if len(existing) > max_count:
                results.append({
                    "level": "error",
                    "code": "port_capacity_exceeded",
                    "message": f"端口 {tgt_id}.{tgt_port} 超出上限 {max_count}（当前 {len(existing)}）",
                    "node_ids": [tgt_id],
                    "edge_ids": [e.get("id", "") for e in existing],
                    "fix": f"删除入边，保留不超过 {max_count} 条",
                })

    # 4. 节点数警告
    if len(nodes) > 80:
        results.append({
            "level": "warning",
            "code": "too_many_nodes",
            "message": f"画布有 {len(nodes)} 个节点，建议拆分以避免性能下降",
            "node_ids": [],
            "edge_ids": [],
            "fix": "将画布拆分为多个子画布",
        })

    # 5. 孤立生成节点警告
    gen_nodes = [n for n in nodes if n.get("type") in GENERATION_NODE_TYPES]
    for gn in gen_nodes:
        has_downstream = any(
            e.get("source") == gn["id"] for e in edges
        )
        if not has_downstream:
            results.append({
                "level": "warning",
                "code": "orphan_generation_node",
                "message": f"生成节点 {gn['id']} 无下游 preview，产物不会被沉淀",
                "node_ids": [gn["id"]],
                "edge_ids": [],
                "fix": "连接一个 preview 节点以保存产物",
            })

    return results


def split_errors(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """将校验结果拆分为 errors 与 warnings。"""
    errors = [i for i in items if i["level"] == "error"]
    warnings = [i for i in items if i["level"] == "warning"]
    return errors, warnings
