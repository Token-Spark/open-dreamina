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

"""画布图算法：纯函数，无 DB 依赖，便于单元测试。

- 拓扑排序（Kahn 算法）
- 环检测
- 上游节点收集
- 入边按 port 分组
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def _build_adjacency(doc: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, int]]:
    """构建邻接表与入度表。

    Returns:
        adj: node_id -> [downstream node_id, ...]
        in_degree: node_id -> 入度
    """
    nodes = doc.get("nodes", [])
    edges = doc.get("edges", [])
    node_ids = {n["id"] for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in node_ids or tgt not in node_ids:
            continue
        adj[src].append(tgt)
        in_degree[tgt] += 1

    return adj, in_degree


def topological_sort(doc: dict[str, Any]) -> tuple[list[str] | None, list[str]]:
    """拓扑排序（Kahn 算法）。

    Returns:
        order: 拓扑有序的 node_id 列表；存在环时返回 None
        cycle_nodes: 若存在环，返回参与环的节点 id（无环时为空列表）
    """
    adj, in_degree = _build_adjacency(doc)
    queue = deque([nid for nid, d in in_degree.items() if d == 0])
    order: list[str] = []
    remaining = dict(in_degree)

    while queue:
        nid = queue.popleft()
        order.append(nid)
        for downstream in adj[nid]:
            remaining[downstream] -= 1
            if remaining[downstream] == 0:
                queue.append(downstream)

    if len(order) != len(in_degree):
        cycle_nodes = [nid for nid, d in remaining.items() if d > 0]
        return None, cycle_nodes
    return order, []


def detect_cycle(doc: dict[str, Any]) -> list[str]:
    """检测文档中是否存在环，返回参与环的节点 id 列表（无环返回空列表）。"""
    _, cycle_nodes = topological_sort(doc)
    return cycle_nodes


def collect_upstream(doc: dict[str, Any], node_id: str) -> list[str]:
    """收集指定节点的所有上游节点（传递闭包），按拓扑顺序返回。

    不含 node_id 自身。
    """
    nodes = doc.get("nodes", [])
    node_ids = {n["id"] for n in nodes}
    if node_id not in node_ids:
        return []

    # 反向邻接表
    reverse_adj: dict[str, list[str]] = defaultdict(list)
    for edge in doc.get("edges", []):
        src = edge.get("source")
        tgt = edge.get("target")
        if src in node_ids and tgt in node_ids:
            reverse_adj[tgt].append(src)

    visited: set[str] = set()
    queue = deque([node_id])
    upstream: list[str] = []

    while queue:
        nid = queue.popleft()
        for parent in reverse_adj.get(nid, []):
            if parent not in visited:
                visited.add(parent)
                upstream.append(parent)
                queue.append(parent)

    # 按拓扑序排列上游
    topo_order, _ = topological_sort(doc)
    if topo_order:
        topo_set = set(upstream)
        upstream = [nid for nid in topo_order if nid in topo_set]

    return upstream


def collect_downstream(doc: dict[str, Any], node_id: str) -> list[str]:
    """收集指定节点的所有下游节点（传递闭包），不含自身。"""
    nodes = doc.get("nodes", [])
    node_ids = {n["id"] for n in nodes}
    if node_id not in node_ids:
        return []

    adj: dict[str, list[str]] = defaultdict(list)
    for edge in doc.get("edges", []):
        src = edge.get("source")
        tgt = edge.get("target")
        if src in node_ids and tgt in node_ids:
            adj[src].append(tgt)

    visited: set[str] = set()
    queue = deque([node_id])
    downstream: list[str] = []

    while queue:
        nid = queue.popleft()
        for child in adj.get(nid, []):
            if child not in visited:
                visited.add(child)
                downstream.append(child)
                queue.append(child)

    return downstream


def edges_to_port(doc: dict[str, Any], target_node: str, target_port: str) -> list[dict[str, Any]]:
    """获取指向某节点某端口的所有入边，按 order 排序。"""
    edges = [
        e for e in doc.get("edges", [])
        if e.get("target") == target_node and e.get("target_port") == target_port
    ]
    edges.sort(key=lambda e: e.get("order", 0))
    return edges


def ordered_upstream_assets(
    doc: dict[str, Any], node_id: str, port: str
) -> list[str]:
    """收集某节点某端口的有序上游产物 asset_id 列表。

    遍历该端口入边（按 order），从每条边的源节点产物中收集 asset_id。
    上游若是 asset 节点，直接取 data.asset_id；
    上游若是生成节点，取其 runtime 产物（从 node_states 投影，P0 中由 run 填充）。
    """
    edges = edges_to_port(doc, node_id, port)
    asset_ids: list[str] = []
    for edge in edges:
        src_id = edge.get("source")
        src_node = _find_node(doc, src_id)
        if not src_node:
            continue
        if src_node.get("type") == "asset":
            aid = src_node.get("data", {}).get("asset_id")
            if aid:
                asset_ids.append(aid)
        else:
            # 生成节点的产物从 runtime 快照读取（由运行编排注入）
            runtime = src_node.get("runtime") or {}
            for aid in runtime.get("output_asset_ids", []):
                asset_ids.append(aid)
    return asset_ids


def resolved_prompt(doc: dict[str, Any], node: dict[str, Any]) -> str | None:
    """解析节点的提示词：上游 prompt 入边优先，回退节点本地值。"""
    prompt_edges = edges_to_port(doc, node["id"], "prompt")
    if prompt_edges:
        parts: list[str] = []
        for edge in prompt_edges:
            src_node = _find_node(doc, edge.get("source"))
            if src_node and src_node.get("type") == "prompt":
                text = src_node.get("data", {}).get("text", "")
                if text:
                    parts.append(text)
        if parts:
            return "\n".join(parts)
    return node.get("data", {}).get("prompt")


def _find_node(doc: dict[str, Any], node_id: str | None) -> dict[str, Any] | None:
    if not node_id:
        return None
    for node in doc.get("nodes", []):
        if node.get("id") == node_id:
            return node
    return None
