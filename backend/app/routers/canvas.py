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

"""画布路由：CRUD + 文档读写 + operations + 校验 + 版本管理 + 运行。"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..canvas_service import (
    CanvasOperationError,
    CanvasValidationError,
    VersionConflict,
    apply_operations,
    create_canvas,
    delete_canvas,
    duplicate_canvas,
    get_canvas,
    get_latest_doc_meta,
    get_template,
    list_canvases,
    list_templates,
    list_versions,
    load_latest_document,
    load_document_version,
    revert_to_version,
    save_document,
)
from ..canvas_specs import NODE_SPECS
from ..canvas_validate import split_errors, validate_document
from ..database import get_db
from ..models import Canvas, CanvasRun
from ..schemas import (
    CanvasCreate,
    CanvasDetail,
    CanvasDocumentPayload,
    CanvasDocumentResponse,
    CanvasDocumentSave,
    CanvasListResponse,
    CanvasOperationResult,
    CanvasOperationsRequest,
    CanvasRevertRequest,
    CanvasRunCreateResponse,
    CanvasRunDetail,
    CanvasRunListResponse,
    CanvasRunRequest,
    CanvasRunSummary,
    CanvasSummary,
    CanvasUpdate,
    CanvasValidation,
    CanvasVersionItem,
    CanvasVersionListResponse,
    MessageResponse,
    NodeSpecResponse,
)
from ..utils.time_utils import now_iso as _now

router = APIRouter(prefix="/canvas", tags=["canvas"])


# ---------------- 辅助函数 ----------------

def _to_summary(canvas: Canvas) -> CanvasSummary:
    tags = json.loads(canvas.tags_json) if canvas.tags_json else []
    return CanvasSummary(
        id=canvas.id,
        name=canvas.name,
        description=canvas.description,
        tags=tags,
        conversation_id=canvas.conversation_id,
        cover_asset_id=canvas.cover_asset_id,
        version=canvas.version,
        node_count=canvas.node_count,
        last_run_at=canvas.last_run_at,
        created_at=canvas.created_at,
        updated_at=canvas.updated_at,
    )


def _to_detail(canvas: Canvas, document: dict[str, Any]) -> CanvasDetail:
    tags = json.loads(canvas.tags_json) if canvas.tags_json else []
    return CanvasDetail(
        id=canvas.id,
        name=canvas.name,
        description=canvas.description,
        tags=tags,
        conversation_id=canvas.conversation_id,
        cover_asset_id=canvas.cover_asset_id,
        version=canvas.version,
        node_count=canvas.node_count,
        last_run_at=canvas.last_run_at,
        created_at=canvas.created_at,
        updated_at=canvas.updated_at,
        document=CanvasDocumentPayload(**{
            "schema_version": document.get("schema_version", 1),
            "viewport": document.get("viewport", {"x": 0, "y": 0, "zoom": 1}),
            "nodes": document.get("nodes", []),
            "edges": document.get("edges", []),
        }),
        runtime={},
    )


def _get_canvas_or_404(db: Session, canvas_id: str) -> Canvas:
    canvas = get_canvas(db, canvas_id)
    if not canvas:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"画布 {canvas_id} 不存在"},
        )
    return canvas


# ---------------- 画布 CRUD ----------------

@router.get("", response_model=CanvasListResponse)
def list_canvases_endpoint(
    search: str | None = Query(None, description="按名称搜索"),
    tags: str | None = Query(None, description="逗号分隔的标签过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CanvasListResponse:
    """分页查询画布列表（不含文档体）。"""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    items, total = list_canvases(
        db, search=search, tags=tag_list, page=page, page_size=page_size
    )
    return CanvasListResponse(
        items=[_to_summary(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CanvasDetail, status_code=201)
def create_canvas_endpoint(
    payload: CanvasCreate, db: Session = Depends(get_db)
) -> CanvasDetail:
    """新建画布，可指定模板或直接传初始文档。"""
    if payload.template_id and payload.template_id not in (
        "blank", "single_image", "img2video", "storyboard"
    ):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_template",
                    "message": f"模板 {payload.template_id} 不存在"},
        )
    canvas = create_canvas(
        db,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        template_id=payload.template_id,
        document=payload.document,
    )
    doc = load_latest_document(db, canvas.id)
    return _to_detail(canvas, doc)


@router.get("/templates/list", response_model=list[dict])
def list_templates_endpoint() -> list[dict]:
    """列出可用画布模板。"""
    return list_templates()


@router.get("/node-specs", response_model=NodeSpecResponse)
def get_node_specs_endpoint() -> NodeSpecResponse:
    """获取节点规格（前后端单一真源）。"""
    return NodeSpecResponse(specs=NODE_SPECS)


@router.get("/{canvas_id}", response_model=CanvasDetail)
def get_canvas_endpoint(
    canvas_id: str, db: Session = Depends(get_db)
) -> CanvasDetail:
    """获取画布详情（含最新文档）。"""
    canvas = _get_canvas_or_404(db, canvas_id)
    doc = load_latest_document(db, canvas_id)
    return _to_detail(canvas, doc)


@router.patch("/{canvas_id}", response_model=CanvasSummary)
def update_canvas_endpoint(
    canvas_id: str,
    payload: CanvasUpdate,
    db: Session = Depends(get_db),
) -> CanvasSummary:
    """修改画布元数据。"""
    canvas = _get_canvas_or_404(db, canvas_id)
    from ..canvas_service import update_canvas
    canvas = update_canvas(
        db, canvas,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
    )
    return _to_summary(canvas)


@router.delete("/{canvas_id}", response_model=MessageResponse)
def delete_canvas_endpoint(
    canvas_id: str, db: Session = Depends(get_db)
) -> MessageResponse:
    """删除画布（级联删除文档与运行记录）。"""
    if not delete_canvas(db, canvas_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"画布 {canvas_id} 不存在"},
        )
    return MessageResponse(message=f"画布 {canvas_id} 已删除")


@router.post("/{canvas_id}/duplicate", response_model=CanvasDetail, status_code=201)
def duplicate_canvas_endpoint(
    canvas_id: str,
    name: str | None = Query(None, description="新画布名称"),
    db: Session = Depends(get_db),
) -> CanvasDetail:
    """复制画布（节点 id 重映射，产物不复制）。"""
    canvas = duplicate_canvas(db, canvas_id, new_name=name)
    if not canvas:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"画布 {canvas_id} 不存在"},
        )
    doc = load_latest_document(db, canvas.id)
    return _to_detail(canvas, doc)


# ---------------- 文档读写 ----------------

@router.get("/{canvas_id}/document", response_model=CanvasDocumentResponse)
def get_document_endpoint(
    canvas_id: str,
    version: int | None = Query(None, description="指定版本号，默认最新"),
    db: Session = Depends(get_db),
) -> CanvasDocumentResponse:
    """获取画布文档。"""
    _get_canvas_or_404(db, canvas_id)
    if version is not None:
        doc_dict = load_document_version(db, canvas_id, version)
        if doc_dict is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "version_not_found",
                        "message": f"版本 v{version} 不存在"},
            )
        return CanvasDocumentResponse(
            version=version,
            document=CanvasDocumentPayload(**{
                "schema_version": doc_dict.get("schema_version", 1),
                "viewport": doc_dict.get("viewport", {"x": 0, "y": 0, "zoom": 1}),
                "nodes": doc_dict.get("nodes", []),
                "edges": doc_dict.get("edges", []),
            }),
        )
    # 最新版本
    canvas = _get_canvas_or_404(db, canvas_id)
    doc_dict = load_latest_document(db, canvas_id)
    doc_meta = get_latest_doc_meta(db, canvas_id)
    return CanvasDocumentResponse(
        version=canvas.version,
        document=CanvasDocumentPayload(**{
            "schema_version": doc_dict.get("schema_version", 1),
            "viewport": doc_dict.get("viewport", {"x": 0, "y": 0, "zoom": 1}),
            "nodes": doc_dict.get("nodes", []),
            "edges": doc_dict.get("edges", []),
        }),
        actor=doc_meta.actor if doc_meta else "user",
        actor_name=doc_meta.actor_name if doc_meta else "",
        change_summary=doc_meta.change_summary if doc_meta else "",
        created_at=doc_meta.created_at if doc_meta else None,
    )


@router.put("/{canvas_id}/document", response_model=CanvasDocumentResponse)
def save_document_endpoint(
    canvas_id: str,
    payload: CanvasDocumentSave,
    db: Session = Depends(get_db),
) -> CanvasDocumentResponse:
    """全量保存文档（乐观锁）。"""
    try:
        new_version = save_document(
            db, canvas_id,
            document=payload.document.model_dump(),
            base_version=payload.base_version,
            actor=payload.actor,
            actor_name=payload.actor_name,
            change_summary=payload.change_summary,
        )
    except VersionConflict as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "version_conflict",
                    "message": str(e),
                    "current_version": e.current,
                    "your_version": e.yours},
        )
    except CanvasValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error",
                    "message": str(e),
                    "errors": e.errors},
        )
    doc = load_latest_document(db, canvas_id)
    return CanvasDocumentResponse(
        version=new_version,
        document=CanvasDocumentPayload(**{
            "schema_version": doc.get("schema_version", 1),
            "viewport": doc.get("viewport", {"x": 0, "y": 0, "zoom": 1}),
            "nodes": doc.get("nodes", []),
            "edges": doc.get("edges", []),
        }),
        actor=payload.actor,
        actor_name=payload.actor_name,
        change_summary=payload.change_summary,
    )


# ---------------- operations 增量操作 ----------------

@router.post("/{canvas_id}/operations", response_model=CanvasOperationResult)
def apply_operations_endpoint(
    canvas_id: str,
    payload: CanvasOperationsRequest,
    db: Session = Depends(get_db),
) -> CanvasOperationResult:
    """事务化应用增量操作（乐观锁）。"""
    _get_canvas_or_404(db, canvas_id)
    ops = [op.model_dump(exclude_none=True) for op in payload.operations]
    try:
        result = apply_operations(
            db, canvas_id, ops,
            base_version=payload.base_version,
            actor=payload.actor,
            actor_name=payload.actor_name,
            summary=payload.change_summary,
        )
    except VersionConflict as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "version_conflict",
                    "message": str(e),
                    "current_version": e.current,
                    "your_version": e.yours},
        )
    except CanvasValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error",
                    "message": str(e),
                    "errors": e.errors},
        )
    except CanvasOperationError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": e.code, "message": str(e)},
        )
    return CanvasOperationResult(**result)


# ---------------- 校验 ----------------

@router.post("/{canvas_id}/validate", response_model=CanvasValidation)
def validate_canvas_endpoint(
    canvas_id: str,
    version: int | None = Query(None, description="指定版本号校验，默认最新"),
    db: Session = Depends(get_db),
) -> CanvasValidation:
    """校验画布文档结构。"""
    _get_canvas_or_404(db, canvas_id)
    if version is not None:
        doc = load_document_version(db, canvas_id, version)
        if doc is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "version_not_found",
                        "message": f"版本 v{version} 不存在"},
            )
    else:
        doc = load_latest_document(db, canvas_id)
    errors, warnings = split_errors(validate_document(doc))
    return CanvasValidation(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ---------------- 版本管理 ----------------

@router.get("/{canvas_id}/versions", response_model=CanvasVersionListResponse)
def list_versions_endpoint(
    canvas_id: str, db: Session = Depends(get_db)
) -> CanvasVersionListResponse:
    """获取版本历史。"""
    _get_canvas_or_404(db, canvas_id)
    versions = list_versions(db, canvas_id)
    return CanvasVersionListResponse(
        items=[CanvasVersionItem(**v) for v in versions]
    )


@router.post("/{canvas_id}/revert", response_model=CanvasDocumentResponse)
def revert_to_version_endpoint(
    canvas_id: str,
    payload: CanvasRevertRequest,
    db: Session = Depends(get_db),
) -> CanvasDocumentResponse:
    """回滚到指定版本（以新版本追加，不删历史）。"""
    _get_canvas_or_404(db, canvas_id)
    try:
        new_version = revert_to_version(db, canvas_id, payload.target_version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(e)})
    doc = load_latest_document(db, canvas_id)
    return CanvasDocumentResponse(
        version=new_version,
        document=CanvasDocumentPayload(**{
            "schema_version": doc.get("schema_version", 1),
            "viewport": doc.get("viewport", {"x": 0, "y": 0, "zoom": 1}),
            "nodes": doc.get("nodes", []),
            "edges": doc.get("edges", []),
        }),
        change_summary=f"回滚到 v{payload.target_version}",
    )


# ---------------- 运行（P0 骨架，仅创建记录） ----------------

@router.post("/{canvas_id}/runs", response_model=CanvasRunCreateResponse, status_code=201)
def create_run_endpoint(
    canvas_id: str,
    payload: CanvasRunRequest,
    db: Session = Depends(get_db),
) -> CanvasRunCreateResponse:
    """创建运行记录（P0 骨架：仅创建记录，调度在 P1 补全）。"""
    canvas = _get_canvas_or_404(db, canvas_id)
    run = CanvasRun(
        id=str(uuid.uuid4()),
        canvas_id=canvas_id,
        doc_version=canvas.version,
        scope=payload.scope,
        target_node_id=payload.node_id if payload.scope != "all" else None,
        status="pending",
        trigger=payload.trigger,
    )
    db.add(run)
    canvas.last_run_at = _now()
    db.commit()
    return CanvasRunCreateResponse(run_id=run.id)


@router.get("/{canvas_id}/runs", response_model=CanvasRunListResponse)
def list_runs_endpoint(
    canvas_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CanvasRunListResponse:
    """获取画布运行历史。"""
    _get_canvas_or_404(db, canvas_id)
    from sqlalchemy import desc
    query = db.query(CanvasRun).filter(CanvasRun.canvas_id == canvas_id)
    total = query.count()
    items = (
        query.order_by(desc(CanvasRun.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CanvasRunListResponse(
        items=[CanvasRunSummary(
            id=r.id, canvas_id=r.canvas_id, doc_version=r.doc_version,
            scope=r.scope, target_node_id=r.target_node_id,
            status=r.status, trigger=r.trigger,
            created_at=r.created_at, completed_at=r.completed_at,
        ) for r in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{canvas_id}/runs/{run_id}", response_model=CanvasRunDetail)
def get_run_endpoint(
    canvas_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> CanvasRunDetail:
    """获取运行详情。"""
    _get_canvas_or_404(db, canvas_id)
    run = db.get(CanvasRun, run_id)
    if not run or run.canvas_id != canvas_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"运行 {run_id} 不存在"},
        )
    node_states = json.loads(run.node_states_json) if run.node_states_json else {}
    return CanvasRunDetail(
        id=run.id, canvas_id=run.canvas_id, doc_version=run.doc_version,
        scope=run.scope, target_node_id=run.target_node_id,
        status=run.status, node_states=node_states,
        error_msg=run.error_msg, trigger=run.trigger,
        created_at=run.created_at, completed_at=run.completed_at,
    )