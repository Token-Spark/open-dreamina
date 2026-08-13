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

"""资产路由：CRUD + 文件/缩略图流式响应 + 批量删除。"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Asset
from ..providers import ProviderError
from ..schemas import (
    AssetAuditRequest,
    AssetListResponse,
    AssetResponse,
    AssetUpdate,
    BatchDeleteRequest,
    BatchDeleteResponse,
    MessageResponse,
)
from ..services.asset_audit_service import check_asset_audit, submit_asset_audit
from ..services.asset_service import create_asset_record, delete_asset_files, resolve_asset_path
from ..utils.file_utils import save_uploaded_file, make_thumbnail, _guess_asset_type

router = APIRouter(prefix="/assets", tags=["assets"])


def _to_response(asset: Asset) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        task_id=asset.task_id,
        type=asset.type,
        file_path=asset.file_path,
        thumbnail_path=asset.thumbnail_path,
        file_size=asset.file_size,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        duration=asset.duration,
        tags=json.loads(asset.tags_json or "[]"),
        is_favorite=bool(asset.is_favorite),
        audit_status=asset.audit_status,
        audit_asset_id=asset.audit_asset_id,
        audit_asset_url=asset.audit_asset_url,
        audit_error=asset.audit_error,
        created_at=asset.created_at,
        file_url=f"/api/v1/assets/{asset.id}/file",
        thumbnail_url=(
            f"/api/v1/assets/{asset.id}/thumbnail" if asset.thumbnail_path else None
        ),
    )


@router.post("/upload", response_model=AssetResponse, status_code=201)
async def upload_asset(file: UploadFile = File(...), db: Session = Depends(get_db)) -> AssetResponse:
    """上传参考图（图生图/图生视频输入），创建资产记录并返回。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": "缺少文件名"})
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": "文件为空"})

    saved = save_uploaded_file(file_bytes, file.filename)
    asset_type = _guess_asset_type(saved.mime_type)
    thumb_rel = make_thumbnail(saved.absolute_path, asset_type) if asset_type == "image" else None

    asset = create_asset_record(
        db=db,
        saved=saved,
        task_id=None,
        asset_type=asset_type,
        thumbnail_rel=thumb_rel,
        tags=[],
    )
    return _to_response(asset)


@router.get("", response_model=AssetListResponse)
def list_assets(
    type: str | None = None,
    tags: str | None = Query(None, description="逗号分隔，资产需包含任一标签"),
    is_favorite: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=200),
    db: Session = Depends(get_db),
) -> AssetListResponse:
    query = db.query(Asset)
    if type:
        query = query.filter(Asset.type == type)
    if is_favorite is not None:
        query = query.filter(Asset.is_favorite == 1 if is_favorite else 0)
    if date_from:
        query = query.filter(Asset.created_at >= date_from)
    if date_to:
        query = query.filter(Asset.created_at <= date_to)

    total = query.count()
    items = (
        query.order_by(desc(Asset.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 标签过滤（SQLite JSON 不可索引，在内存中过滤）
    if tags:
        wanted = {t.strip() for t in tags.split(",") if t.strip()}
        filtered = []
        for a in items:
            atags = set(json.loads(a.tags_json or "[]"))
            if atags & wanted:
                filtered.append(a)
        items = filtered

    return AssetListResponse(
        items=[_to_response(a) for a in items],
        total=total if not tags else len(items),
        page=page,
        page_size=page_size,
    )


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: str, db: Session = Depends(get_db)) -> AssetResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"资产 {asset_id} 不存在"})
    return _to_response(asset)


@router.post("/{asset_id}/audit", response_model=AssetResponse)
async def audit_asset(
    asset_id: str,
    payload: AssetAuditRequest,
    db: Session = Depends(get_db),
) -> AssetResponse:
    """提交 Seedance 参考素材审核（Spark Hub seedance_asset_audit/submit）。

    仅 Spark Hub Seedance 生视频需要；提交后素材进入 pending 审核中状态。
    """
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"资产 {asset_id} 不存在"})
    try:
        asset = await submit_asset_audit(db, asset, payload.provider)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail={"code": "audit_failed", "message": str(e)})
    return _to_response(asset)


@router.get("/{asset_id}/audit", response_model=AssetResponse)
async def get_asset_audit(
    asset_id: str,
    provider: str = Query(..., description="Spark Hub Seedance Provider slug"),
    db: Session = Depends(get_db),
) -> AssetResponse:
    """查询 Seedance 参考素材审核状态（Spark Hub seedance_asset_audit/status）。

    素材处于 pending 时主动向 Spark Hub 查询一次并刷新本地状态，供前端异步轮询。
    """
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"资产 {asset_id} 不存在"})
    if asset.audit_status == "pending":
        try:
            asset = await check_asset_audit(db, asset, provider)
        except ProviderError as e:
            raise HTTPException(status_code=400, detail={"code": "audit_check_failed", "message": str(e)})
    return _to_response(asset)


@router.get("/{asset_id}/file")
def get_asset_file(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"资产 {asset_id} 不存在"})

    path = resolve_asset_path(asset, "file")
    if not path:
        raise HTTPException(status_code=404, detail={"code": "file_missing", "message": "原始文件不存在"})

    media_type = asset.mime_type or (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return FileResponse(path=path, media_type=media_type, filename=path.name)


@router.get("/{asset_id}/thumbnail")
def get_asset_thumbnail(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"资产 {asset_id} 不存在"})

    path = resolve_asset_path(asset, "thumbnail")
    if not path:
        # 回退到原图（部分老资产可能没有缩略图）
        path = resolve_asset_path(asset, "file")
    if not path:
        raise HTTPException(status_code=404, detail={"code": "file_missing", "message": "缩略图不存在"})

    return FileResponse(path=path, media_type="image/webp")


@router.patch("/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
) -> AssetResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"资产 {asset_id} 不存在"})

    if payload.tags is not None:
        asset.tags_json = json.dumps(payload.tags, ensure_ascii=False)
    if payload.is_favorite is not None:
        asset.is_favorite = 1 if payload.is_favorite else 0

    db.commit()
    db.refresh(asset)
    return _to_response(asset)


@router.delete("/{asset_id}", response_model=MessageResponse)
def delete_asset(asset_id: str, db: Session = Depends(get_db)) -> MessageResponse:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"资产 {asset_id} 不存在"})

    delete_asset_files(asset)
    db.delete(asset)
    db.commit()
    return MessageResponse(message=f"资产 {asset_id} 已删除")


@router.post("/batch-delete", response_model=BatchDeleteResponse)
def batch_delete_assets(
    payload: BatchDeleteRequest,
    db: Session = Depends(get_db),
) -> BatchDeleteResponse:
    deleted: list[str] = []
    failed: list[str] = []
    for aid in payload.asset_ids:
        asset = db.get(Asset, aid)
        if not asset:
            failed.append(aid)
            continue
        try:
            delete_asset_files(asset)
            db.delete(asset)
            deleted.append(aid)
        except Exception:
            failed.append(aid)
    db.commit()
    return BatchDeleteResponse(deleted=deleted, failed=failed)
