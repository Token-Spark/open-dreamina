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

"""画布节点规格：端口定义与连接规则的单一真源。

前端通过 GET /canvas/node-specs 拉取同一份声明，避免规则漂移。
新增节点类型只需在此追加一条规格。
"""
from __future__ import annotations

from typing import Any

# 端口类型枚举
PORT_TYPES = ("image", "video", "audio", "text")

# P0 节点类型
NODE_TYPES = ("asset", "prompt", "image_gen", "video_gen", "preview", "note")

# 本地求值节点（不创建 Task）
LOCAL_NODE_TYPES = ("asset", "prompt", "preview", "note")

# 生成节点（创建 Task）
GENERATION_NODE_TYPES = ("image_gen", "video_gen")

NODE_SPECS: dict[str, dict[str, Any]] = {
    "asset": {
        "inputs": [],
        "outputs": [{"id": "out", "types": ["image", "video", "audio"]}],
    },
    "prompt": {
        "inputs": [{"id": "in", "types": ["text"], "multi": True}],
        "outputs": [{"id": "out", "types": ["text"]}],
    },
    "image_gen": {
        "inputs": [
            {"id": "ref", "types": ["image"], "multi": True, "max": 14},
            {"id": "prompt", "types": ["text"]},
        ],
        "outputs": [{"id": "out", "types": ["image"]}],
    },
    "video_gen": {
        "inputs": [
            {"id": "ref", "types": ["image"], "multi": True, "max": 9},
            {"id": "video", "types": ["video"], "multi": True, "max": 3},
            {"id": "audio", "types": ["audio"], "multi": True, "max": 3},
            {"id": "prompt", "types": ["text"]},
        ],
        "outputs": [{"id": "out", "types": ["video"]}],
    },
    "preview": {
        "inputs": [{"id": "in", "types": ["image", "video", "audio", "text"]}],
        "outputs": [],
    },
    "note": {
        "inputs": [],
        "outputs": [],
    },
}


def get_port_spec(node_type: str, port_id: str, direction: str) -> dict[str, Any] | None:
    """查找节点的某个端口规格。

    Args:
        node_type: 节点类型
        port_id: 端口 id（如 "ref", "out"）
        direction: "inputs" 或 "outputs"

    Returns: 端口规格 dict，未找到返回 None
    """
    spec = NODE_SPECS.get(node_type)
    if not spec:
        return None
    for port in spec.get(direction, []):
        if port["id"] == port_id:
            return port
    return None


def is_port_type_compatible(out_types: list[str], in_types: list[str]) -> bool:
    """输出端口类型与输入端口类型的交集非空即合法。"""
    return bool(set(out_types) & set(in_types))


def get_multi_port_edges(doc: dict[str, Any], target_node: str, target_port: str) -> list[dict[str, Any]]:
    """获取指向某节点某端口的所有入边（按 order 排序）。"""
    edges = [
        e for e in doc.get("edges", [])
        if e.get("target") == target_node and e.get("target_port") == target_port
    ]
    edges.sort(key=lambda e: e.get("order", 0))
    return edges
