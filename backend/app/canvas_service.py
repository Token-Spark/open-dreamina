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

"""画布服务层：文档读写、版本管理、operations 应用。

职责分离：
- 本模块管「文档是什么」（CRUD / 乐观锁 / operations）
- canvas_run_service 管「怎么跑」（P1）
- canvas_graph / canvas_validate 是纯函数，无 DB 依赖
"""
from __future__ import annotations

import copy
import json
import uuid
from typing import Any

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from .canvas_graph import _find_node, edges_to_port
from .canvas_validate import validate_document
from .models import Canvas, CanvasDocument, CanvasRun
from .utils.time_utils import now_iso as _now

# 版本快照保留数
_KEEP_VERSIONS = 30

# 空白画布模板
_EMPTY_DOC: dict[str, Any] = {
    "schema_version": 1,
    "viewport": {"x": 0, "y": 0, "zoom": 1},
    "nodes": [],
    "edges": [],
}

# 本地求值节点（不创建 Task）
LOCAL_NODE_TYPES = ("asset", "prompt", "preview", "note")
# 生成节点（创建 Task）
GENERATION_NODE_TYPES = ("image_gen", "video_gen")


# ---------------- 模板 ----------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "blank": _EMPTY_DOC,
    "single_image": {
        "schema_version": 1,
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "nodes": [
            {"id": "nd_prompt1", "type": "prompt", "position": {"x": 80, "y": 200},
             "data": {"text": "输入提示词"}},
            {"id": "nd_gen1", "type": "image_gen", "position": {"x": 400, "y": 200},
             "data": {"provider": "", "model_id": "", "prompt": "", "params": {}, "batch": 1}},
            {"id": "nd_preview1", "type": "preview", "position": {"x": 720, "y": 200},
             "data": {}},
        ],
        "edges": [
            {"id": "eg_1", "source": "nd_prompt1", "source_port": "out",
             "target": "nd_gen1", "target_port": "prompt", "order": 0},
            {"id": "eg_2", "source": "nd_gen1", "source_port": "out",
             "target": "nd_preview1", "target_port": "in", "order": 0},
        ],
    },
    "img2video": {
        "schema_version": 1,
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "nodes": [
            {"id": "nd_asset1", "type": "asset", "position": {"x": 80, "y": 160},
             "data": {"source": "asset", "asset_id": None, "media_role": "image"},
             "title": "人物/场景图"},
            {"id": "nd_prompt1", "type": "prompt", "position": {"x": 80, "y": 320},
             "data": {"text": "输入提示词"}},
            {"id": "nd_imggen1", "type": "image_gen", "position": {"x": 400, "y": 160},
             "data": {"provider": "", "model_id": "", "prompt": "", "params": {}, "batch": 1}},
            {"id": "nd_vidgen1", "type": "video_gen", "position": {"x": 720, "y": 160},
             "data": {"provider": "", "model_id": "", "prompt": "", "params": {},
                      "frame_mode": "auto"}},
            {"id": "nd_preview1", "type": "preview", "position": {"x": 1040, "y": 160},
             "data": {}},
        ],
        "edges": [
            {"id": "eg_1", "source": "nd_asset1", "source_port": "out",
             "target": "nd_imggen1", "target_port": "ref", "order": 0},
            {"id": "eg_2", "source": "nd_prompt1", "source_port": "out",
             "target": "nd_imggen1", "target_port": "prompt", "order": 0},
            {"id": "eg_3", "source": "nd_imggen1", "source_port": "out",
             "target": "nd_vidgen1", "target_port": "ref", "order": 0},
            {"id": "eg_4", "source": "nd_vidgen1", "source_port": "out",
             "target": "nd_preview1", "target_port": "in", "order": 0},
        ],
    },
    "storyboard": {
        "schema_version": 1,
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "nodes": [
            {"id": "nd_prompt1", "type": "prompt", "position": {"x": 80, "y": 160},
             "data": {"text": "场景描述"}},
            {"id": "nd_gen1", "type": "image_gen", "position": {"x": 400, "y": 160},
             "data": {"provider": "", "model_id": "", "prompt": "", "params": {}, "batch": 1},
             "title": "分镜 1"},
            {"id": "nd_gen2", "type": "image_gen", "position": {"x": 400, "y": 360},
             "data": {"provider": "", "model_id": "", "prompt": "", "params": {}, "batch": 1},
             "title": "分镜 2"},
            {"id": "nd_gen3", "type": "image_gen", "position": {"x": 400, "y": 560},
             "data": {"provider": "", "model_id": "", "prompt": "", "params": {}, "batch": 1},
             "title": "分镜 3"},
            {"id": "nd_preview1", "type": "preview", "position": {"x": 720, "y": 360},
             "data": {}},
        ],
        "edges": [
            {"id": "eg_1", "source": "nd_prompt1", "source_port": "out",
             "target": "nd_gen1", "target_port": "prompt", "order": 0},
            {"id": "eg_2", "source": "nd_prompt1", "source_port": "out",
             "target": "nd_gen2", "target_port": "prompt", "order": 0},
            {"id": "eg_3", "source": "nd_prompt1", "source_port": "out",
             "target": "nd_gen3", "target_port": "prompt", "order": 0},
            {"id": "eg_4", "source": "nd_gen1", "source_port": "out",
             "target": "nd_preview1", "target_port": "in", "order": 0},
        ],
    },
}


def get_template(template_id: str) -> dict[str, Any] | None:
    return copy.deepcopy(_TEMPLATES.get(template_id))


def list_templates() -> list[dict[str, str]]:
    return [
        {"id": "blank", "name": "空白画布"},
        {"id": "single_image", "name": "单图生成"},
        {"id": "img2video", "name": "图生视频"},
        {"id": "storyboard", "name": "分镜批量"},
    ]


# ---------------- 自定义异常 ----------------

class VersionConflict(Exception):
    """乐观锁版本不匹配。"""

    def __init__(self, current: int, yours: int):
        self.current = current
        self.yours = yours
        super().__init__(f"版本冲突: 当前 v{current}，你基于 v{yours}")


class CanvasValidationError(Exception):
    """结构校验未通过。"""

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        super().__init__(f"校验失败: {len(errors)} 个错误")


class CanvasOperationError(Exception):
    """单个操作非法。"""

    def __init__(self, code: str, op: str, message: str):
        self.code = code
        self.op = op
        super().__init__(f"[{code}] {op}: {message}")


# ---------------- 画布 CRUD ----------------

def create_canvas(
    db: Session,
    name: str | None = None,
    description: str = "",
    tags: list[str] | None = None,
    template_id: str | None = None,
    document: dict[str, Any] | None = None,
) -> Canvas:
    """新建画布，初始化第一个版本文档。"""
    canvas_id = str(uuid.uuid4())
    canvas = Canvas(
        id=canvas_id,
        name=name or "未命名画布",
        description=description,
        tags_json=json.dumps(tags or [], ensure_ascii=False),
    )
    db.add(canvas)
    db.flush()

    if document:
        doc = copy.deepcopy(document)
    elif template_id and template_id in _TEMPLATES:
        doc = copy.deepcopy(_TEMPLATES[template_id])
    else:
        doc = copy.deepcopy(_EMPTY_DOC)
    doc.setdefault("schema_version", 1)
    doc.setdefault("viewport", {"x": 0, "y": 0, "zoom": 1})
    doc.setdefault("nodes", [])
    doc.setdefault("edges", [])

    version = CanvasDocument(
        id=str(uuid.uuid4()),
        canvas_id=canvas_id,
        version=1,
        doc_json=json.dumps(doc, ensure_ascii=False),
        actor="user",
        actor_name="",
        change_summary="初始化画布",
    )
    db.add(version)
    canvas.node_count = len(doc.get("nodes", []))
    db.commit()
    db.refresh(canvas)
    return canvas


def get_canvas(db: Session, canvas_id: str) -> Canvas | None:
    return db.get(Canvas, canvas_id)


def update_canvas(
    db: Session,
    canvas: Canvas,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> Canvas:
    if name is not None:
        canvas.name = name
    if description is not None:
        canvas.description = description
    if tags is not None:
        canvas.tags_json = json.dumps(tags, ensure_ascii=False)
    canvas.updated_at = _now()
    db.commit()
    db.refresh(canvas)
    return canvas


def delete_canvas(db: Session, canvas_id: str) -> bool:
    """删除画布（文档与运行记录级联）。"""
    canvas = db.get(Canvas, canvas_id)
    if not canvas:
        return False
    db.delete(canvas)
    db.commit()
    return True


def duplicate_canvas(db: Session, canvas_id: str, new_name: str | None = None) -> Canvas | None:
    """复制画布：节点 id 重映射，产物不复制。"""
    src = db.get(Canvas, canvas_id)
    if not src:
        return None

    doc = load_latest_document(db, canvas_id)
    id_map: dict[str, str] = {}
    for node in doc.get("nodes", []):
        old_id = node["id"]
        new_id = f"nd_{uuid.uuid4().hex[:8]}"
        id_map[old_id] = new_id
        node["id"] = new_id

    for edge in doc.get("edges", []):
        edge["id"] = f"eg_{uuid.uuid4().hex[:8]}"
        if edge.get("source") in id_map:
            edge["source"] = id_map[edge["source"]]
        if edge.get("target") in id_map:
            edge["target"] = id_map[edge["target"]]

    return create_canvas(
        db,
        name=new_name or f"{src.name} 副本",
        description=src.description,
        tags=json.loads(src.tags_json) if src.tags_json else [],
        document=doc,
    )


def list_canvases(
    db: Session,
    search: str | None = None,
    tags: list[str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Canvas], int]:
    """分页查询画布，不含文档体。"""
    query = db.query(Canvas)
    if search:
        query = query.filter(Canvas.name.contains(search))
    if tags:
        # 标签过滤下推到 SQL：tags_json 存储为 JSON 数组，逐标签 LIKE 匹配
        tag_conditions = [Canvas.tags_json.contains(f'"{t}"') for t in tags]
        query = query.filter(or_(*tag_conditions))
    total = query.count()
    items = (
        query.order_by(desc(Canvas.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


# ---------------- 文档读写 ----------------

def load_latest_document(db: Session, canvas_id: str) -> dict[str, Any]:
    """加载最新版本文档。"""
    doc_row = (
        db.query(CanvasDocument)
        .filter(CanvasDocument.canvas_id == canvas_id)
        .order_by(desc(CanvasDocument.version))
        .first()
    )
    if not doc_row:
        return copy.deepcopy(_EMPTY_DOC)
    return json.loads(doc_row.doc_json)


def load_document_version(db: Session, canvas_id: str, version: int) -> dict[str, Any] | None:
    doc_row = (
        db.query(CanvasDocument)
        .filter(CanvasDocument.canvas_id == canvas_id, CanvasDocument.version == version)
        .first()
    )
    if not doc_row:
        return None
    return json.loads(doc_row.doc_json)


def get_latest_doc_meta(db: Session, canvas_id: str) -> CanvasDocument | None:
    return (
        db.query(CanvasDocument)
        .filter(CanvasDocument.canvas_id == canvas_id)
        .order_by(desc(CanvasDocument.version))
        .first()
    )


def save_document(
    db: Session,
    canvas_id: str,
    document: dict[str, Any],
    base_version: int,
    actor: str = "user",
    actor_name: str = "",
    change_summary: str = "",
) -> int:
    """全量保存文档（乐观锁）。返回新版本号。"""
    canvas = db.get(Canvas, canvas_id)
    if not canvas:
        raise ValueError(f"画布 {canvas_id} 不存在")

    if base_version != canvas.version:
        raise VersionConflict(current=canvas.version, yours=base_version)

    errors = validate_document(document)
    error_items = [e for e in errors if e["level"] == "error"]
    if error_items:
        raise CanvasValidationError(error_items)

    new_version = canvas.version + 1
    doc = CanvasDocument(
        id=str(uuid.uuid4()),
        canvas_id=canvas_id,
        version=new_version,
        doc_json=json.dumps(document, ensure_ascii=False),
        actor=actor,
        actor_name=actor_name,
        change_summary=change_summary or "保存文档",
    )
    db.add(doc)
    canvas.version = new_version
    canvas.node_count = len(document.get("nodes", []))
    canvas.updated_at = _now()
    db.commit()
    db.refresh(canvas)

    _prune_old_documents(db, canvas_id)
    return new_version


def list_versions(db: Session, canvas_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(CanvasDocument)
        .filter(CanvasDocument.canvas_id == canvas_id)
        .order_by(desc(CanvasDocument.version))
        .all()
    )
    return [
        {
            "version": r.version,
            "actor": r.actor,
            "actor_name": r.actor_name,
            "change_summary": r.change_summary,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def revert_to_version(db: Session, canvas_id: str, target_version: int) -> int:
    """回滚到指定版本（以新版本追加，不删历史）。"""
    canvas = db.get(Canvas, canvas_id)
    if not canvas:
        raise ValueError(f"画布 {canvas_id} 不存在")

    doc_dict = load_document_version(db, canvas_id, target_version)
    if doc_dict is None:
        raise ValueError(f"版本 v{target_version} 不存在")

    new_version = canvas.version + 1
    doc_row = CanvasDocument(
        id=str(uuid.uuid4()),
        canvas_id=canvas_id,
        version=new_version,
        doc_json=json.dumps(doc_dict, ensure_ascii=False),
        actor="user",
        actor_name="",
        change_summary=f"回滚到 v{target_version}",
    )
    db.add(doc_row)
    canvas.version = new_version
    canvas.node_count = len(doc_dict.get("nodes", []))
    canvas.updated_at = _now()
    db.commit()
    db.refresh(canvas)

    _prune_old_documents(db, canvas_id)
    return new_version


def _prune_old_documents(db: Session, canvas_id: str) -> None:
    """修剪旧版本，只保留最近 _KEEP_VERSIONS 版。"""
    rows = (
        db.query(CanvasDocument)
        .filter(CanvasDocument.canvas_id == canvas_id)
        .order_by(desc(CanvasDocument.version))
        .all()
    )
    for row in rows[_KEEP_VERSIONS:]:
        db.delete(row)
    db.commit()


# ---------------- operations 增量操作 ----------------

def apply_operations(
    db: Session,
    canvas_id: str,
    ops: list[dict[str, Any]],
    base_version: int | None,
    actor: str,
    actor_name: str,
    summary: str,
) -> dict[str, Any]:
    """事务化应用增量操作：CAS 检查 → 逐条应用 → 全图校验 → 落新版本。

    任一操作非法则整体回滚，绝不留下半成品文档。
    """
    canvas = get_canvas(db, canvas_id)
    if not canvas:
        raise ValueError(f"画布 {canvas_id} 不存在")

    if base_version is not None and base_version != canvas.version:
        raise VersionConflict(current=canvas.version, yours=base_version)

    doc = load_latest_document(db, canvas_id)
    working = copy.deepcopy(doc)
    applied: list[dict[str, Any]] = []

    for op in ops:
        op_type = op.get("op", "")
        handler = _OP_HANDLERS.get(op_type)
        if handler is None:
            raise CanvasOperationError(
                code="unknown_op", op=op_type, message="未知操作类型")
        result = handler(working, op)
        applied.append(result)
        # set_canvas_meta 直接修改 canvas 模型
        if op_type == "set_canvas_meta":
            if result.get("name") is not None:
                canvas.name = result["name"]
            if result.get("description") is not None:
                canvas.description = result["description"]
            if result.get("tags") is not None:
                canvas.tags_json = json.dumps(
                    result["tags"], ensure_ascii=False)

    # 全图校验
    errors = validate_document(working)
    error_items = [e for e in errors if e["level"] == "error"]
    if error_items:
        raise CanvasValidationError(error_items)

    # 落新版本
    new_version = canvas.version + 1
    doc_row = CanvasDocument(
        id=str(uuid.uuid4()),
        canvas_id=canvas_id,
        version=new_version,
        doc_json=json.dumps(working, ensure_ascii=False),
        actor=actor,
        actor_name=actor_name,
        change_summary=summary or "应用操作",
    )
    db.add(doc_row)
    canvas.version = new_version
    canvas.node_count = len(working.get("nodes", []))
    canvas.updated_at = _now()
    db.commit()
    db.refresh(canvas)

    _prune_old_documents(db, canvas_id)

    warnings = [e for e in errors if e["level"] == "warning"]
    return {"version": new_version, "applied": applied, "warnings": warnings}


# ---------------- 操作处理器（表驱动分派） ----------------

def _op_add_node(working: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """添加节点。"""
    node = op.get("node")
    if not node or "id" not in node:
        raise CanvasOperationError(
            code="invalid_op", op="add_node", message="缺少 node 或 node.id")

    if _find_node(working, node["id"]):
        raise CanvasOperationError(
            code="duplicate_node", op="add_node",
            message=f"节点 {node['id']} 已存在")

    node.setdefault("type", "")
    node.setdefault("position", {"x": 0, "y": 0})
    node.setdefault("data", {})
    working.setdefault("nodes", []).append(node)
    return {"op": "add_node", "node_id": node["id"]}


def _op_remove_node(working: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """删除节点及其关联边。"""
    node_id = op.get("node_id")
    if not node_id:
        raise CanvasOperationError(
            code="invalid_op", op="remove_node", message="缺少 node_id")

    if not _find_node(working, node_id):
        raise CanvasOperationError(
            code="node_not_found", op="remove_node",
            message=f"节点 {node_id} 不存在")

    working["nodes"] = [
        n for n in working.get("nodes", []) if n.get("id") != node_id
    ]
    removed_edges = [
        e for e in working.get("edges", [])
        if e.get("source") == node_id or e.get("target") == node_id
    ]
    working["edges"] = [
        e for e in working.get("edges", [])
        if e.get("source") != node_id and e.get("target") != node_id
    ]
    return {"op": "remove_node", "node_id": node_id,
            "removed_edges": len(removed_edges)}


def _op_update_node_data(
    working: dict[str, Any], op: dict[str, Any]
) -> dict[str, Any]:
    """更新节点 data（patch 合并）。"""
    node_id = op.get("node_id")
    patch = op.get("patch")
    if not node_id:
        raise CanvasOperationError(
            code="invalid_op", op="update_node_data", message="缺少 node_id")
    if not patch:
        raise CanvasOperationError(
            code="invalid_op", op="update_node_data", message="缺少 patch")

    node = _find_node(working, node_id)
    if not node:
        raise CanvasOperationError(
            code="node_not_found", op="update_node_data",
            message=f"节点 {node_id} 不存在")

    node.setdefault("data", {})
    node["data"].update(patch)
    return {"op": "update_node_data", "node_id": node_id,
            "patched_keys": list(patch.keys())}


def _op_set_position(working: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """设置节点位置。"""
    node_id = op.get("node_id")
    position = op.get("position")
    if not node_id:
        raise CanvasOperationError(
            code="invalid_op", op="set_position", message="缺少 node_id")
    if not position:
        raise CanvasOperationError(
            code="invalid_op", op="set_position", message="缺少 position")

    node = _find_node(working, node_id)
    if not node:
        raise CanvasOperationError(
            code="node_not_found", op="set_position",
            message=f"节点 {node_id} 不存在")

    node["position"] = {"x": position.get("x", 0), "y": position.get("y", 0)}
    return {"op": "set_position", "node_id": node_id}


def _op_add_edge(working: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """添加边。"""
    edge = op.get("edge")
    if not edge or "id" not in edge:
        raise CanvasOperationError(
            code="invalid_op", op="add_edge", message="缺少 edge 或 edge.id")

    if any(e.get("id") == edge["id"] for e in working.get("edges", [])):
        raise CanvasOperationError(
            code="duplicate_edge", op="add_edge",
            message=f"边 {edge['id']} 已存在")

    edge.setdefault("source", "")
    edge.setdefault("target", "")
    edge.setdefault("source_port", "")
    edge.setdefault("target_port", "")
    edge.setdefault("order", 0)
    working.setdefault("edges", []).append(edge)
    return {"op": "add_edge", "edge_id": edge["id"]}


def _op_remove_edge(working: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """删除边。"""
    edge_id = op.get("edge_id")
    if not edge_id:
        raise CanvasOperationError(
            code="invalid_op", op="remove_edge", message="缺少 edge_id")

    edges = working.get("edges", [])
    edge = next((e for e in edges if e.get("id") == edge_id), None)
    if not edge:
        raise CanvasOperationError(
            code="edge_not_found", op="remove_edge",
            message=f"边 {edge_id} 不存在")

    working["edges"] = [e for e in edges if e.get("id") != edge_id]
    return {"op": "remove_edge", "edge_id": edge_id}


def _op_reorder_edge(working: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    """调整边在目标端口的 order。"""
    edge_id = op.get("edge_id")
    new_order = op.get("order")
    if not edge_id:
        raise CanvasOperationError(
            code="invalid_op", op="reorder_edge", message="缺少 edge_id")
    if new_order is None:
        raise CanvasOperationError(
            code="invalid_op", op="reorder_edge", message="缺少 order")

    edges = working.get("edges", [])
    edge = next((e for e in edges if e.get("id") == edge_id), None)
    if not edge:
        raise CanvasOperationError(
            code="edge_not_found", op="reorder_edge",
            message=f"边 {edge_id} 不存在")

    old_order = edge.get("order", 0)
    edge["order"] = new_order
    return {"op": "reorder_edge", "edge_id": edge_id,
            "old_order": old_order, "new_order": new_order}


def _op_set_canvas_meta(
    working: dict[str, Any], op: dict[str, Any]
) -> dict[str, Any]:
    """更新画布元数据（名称/描述/标签），不修改文档图结构。"""
    result: dict[str, Any] = {"op": "set_canvas_meta"}
    if op.get("name") is not None:
        result["name"] = op["name"]
    if op.get("description") is not None:
        result["description"] = op["description"]
    if op.get("tags") is not None:
        result["tags"] = op["tags"]
    return result


# 操作分派表
_OP_HANDLERS: dict[str, Any] = {
    "add_node": _op_add_node,
    "remove_node": _op_remove_node,
    "update_node_data": _op_update_node_data,
    "set_position": _op_set_position,
    "add_edge": _op_add_edge,
    "remove_edge": _op_remove_edge,
    "reorder_edge": _op_reorder_edge,
    "set_canvas_meta": _op_set_canvas_meta,
}
