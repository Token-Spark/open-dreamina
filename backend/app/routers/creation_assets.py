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

"""创作资产（素材库）路由：CRUD + 标签汇总 + 项目管理 + 云同步/拉取。

信任模型：能访问同一云存储的成员均可信，全部资产可编辑；
推送侧由乐观锁（CAS）保证绝不盲覆盖他人更新。
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Asset, CreationAsset
from ..providers import ProviderError
from ..schemas import (
    CreationAssetCreate,
    CreationAssetListResponse,
    CreationAssetResponse,
    CreationAssetTagResponse,
    CreationAssetUpdate,
    MessageResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    SyncConfigResponse,
    SyncConfigUpdate,
    SyncResultResponse,
    TagSyncRequest,
)
from ..services import creation_asset_service as svc
from ..services import qiniu_service

router = APIRouter(prefix="/creation-assets", tags=["creation-assets"])


def _to_response(ca: CreationAsset, owner_id: str) -> CreationAssetResponse:
    image_url = (
        f"/api/v1/assets/{ca.image_asset_id}/file" if ca.image_asset_id else None
    )
    audio_url = (
        f"/api/v1/assets/{ca.audio_asset_id}/file" if ca.audio_asset_id else None
    )
    # 拉取导入的资产已生成缩略图；直接复用其缩略图接口
    image_thumb = (
        f"/api/v1/assets/{ca.image_asset_id}/thumbnail" if ca.image_asset_id else None
    )
    # 近似判断「有未推送修改」：编辑必然更新 updated_at，避免每次请求读文件算指纹
    pending = bool(ca.updated_at and (not ca.synced_at or ca.updated_at > ca.synced_at))
    return CreationAssetResponse(
        id=ca.id,
        name=ca.name,
        category=ca.category,
        description=ca.description,
        image_asset_id=ca.image_asset_id,
        audio_asset_id=ca.audio_asset_id,
        tags=json.loads(ca.tags_json or "[]"),
        owner_id=ca.owner_id,
        owner_name=ca.owner_name,
        origin=ca.origin,
        is_mine=ca.owner_id == owner_id,
        synced_at=ca.synced_at,
        created_at=ca.created_at,
        updated_at=ca.updated_at,
        base_version=ca.base_version or 0,
        cloud_tag=ca.cloud_tag or "",
        has_pending_changes=pending,
        image_url=image_url,
        image_thumbnail_url=image_thumb,
        audio_url=audio_url,
    )


@router.get("", response_model=CreationAssetListResponse)
def list_creation_assets(
    category: str | None = Query(None, pattern="^(character|scene|prop)$"),
    tags: str | None = Query(None, description="逗号分隔，资产需包含任一标签"),
    search: str | None = Query(None, description="按名称/描述模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> CreationAssetListResponse:
    owner_id, _ = svc.get_or_create_owner(db)
    query = db.query(CreationAsset)
    if category:
        query = query.filter(CreationAsset.category == category)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(CreationAsset.name.like(like), CreationAsset.description.like(like))
        )
    total = query.count()
    items = (
        query.order_by(desc(CreationAsset.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    # 标签过滤（SQLite JSON 不可索引，内存过滤，与 assets 路由一致）
    if tags:
        wanted = {t.strip() for t in tags.split(",") if t.strip()}
        items = [a for a in items if set(json.loads(a.tags_json or "[]")) & wanted]
    return CreationAssetListResponse(
        items=[_to_response(a, owner_id) for a in items],
        total=total if not tags else len(items),
        page=page,
        page_size=page_size,
    )


@router.get("/tags", response_model=CreationAssetTagResponse)
def list_creation_asset_tags(db: Session = Depends(get_db)) -> CreationAssetTagResponse:
    """标签汇总（含计数），驱动筛选与「按标签同步」。"""
    counter: dict[str, int] = {}
    for ca in db.query(CreationAsset).all():
        for t in set(json.loads(ca.tags_json or "[]")):
            counter[t] = counter.get(t, 0) + 1
    tags = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return CreationAssetTagResponse(tags=[{"name": n, "count": c} for n, c in tags])


# ---------------- 同步配置与项目 ----------------

@router.get("/sync/status", response_model=SyncConfigResponse)
def get_sync_status(db: Session = Depends(get_db)) -> SyncConfigResponse:
    owner_id, owner_name = svc.get_or_create_owner(db)
    return SyncConfigResponse(
        owner_id=owner_id,
        owner_name=owner_name,
        qiniu_configured=qiniu_service.is_configured(),
    )


@router.put("/sync/status", response_model=SyncConfigResponse)
def update_sync_status(
    payload: SyncConfigUpdate, db: Session = Depends(get_db)
) -> SyncConfigResponse:
    """修改同步展示名（云端目录由 owner_id 决定，改名不影响已同步对象）。"""
    owner_id, owner_name = svc.update_owner_name(db, payload.owner_name.strip())
    return SyncConfigResponse(
        owner_id=owner_id,
        owner_name=owner_name,
        qiniu_configured=qiniu_service.is_configured(),
    )


def _require_qiniu() -> None:
    if not qiniu_service.is_configured():
        raise HTTPException(
            400,
            detail={
                "code": "qiniu_not_configured",
                "message": "未配置七牛云存储，请在 .env 中设置 QINIU_* 相关配置后重启服务",
            },
        )


@router.get("/projects", response_model=ProjectListResponse)
def list_projects() -> ProjectListResponse:
    """列举云端全部团队项目。"""
    _require_qiniu()
    try:
        projects = svc.list_projects()
    except ProviderError as e:
        raise HTTPException(400, detail={"code": "project_list_failed", "message": str(e)})
    return ProjectListResponse(items=[ProjectResponse(**p) for p in projects])


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(
    payload: ProjectCreate, db: Session = Depends(get_db)
) -> ProjectResponse:
    """创建团队项目（云端目录 + project.json）。"""
    _require_qiniu()
    try:
        project = svc.create_project(db, payload.name.strip(), payload.description)
    except ProviderError as e:
        raise HTTPException(400, detail={"code": "project_create_failed", "message": str(e)})
    return ProjectResponse(**project)


# ---------------- CRUD ----------------

@router.post("", response_model=CreationAssetResponse, status_code=201)
def create_creation_asset(
    payload: CreationAssetCreate, db: Session = Depends(get_db)
) -> CreationAssetResponse:
    owner_id, owner_name = svc.get_or_create_owner(db)
    _validate_media_refs(db, payload.image_asset_id, payload.audio_asset_id)
    ca = CreationAsset(
        id=uuid.uuid4().hex,
        name=payload.name.strip(),
        category=payload.category,
        description=payload.description or "",
        image_asset_id=payload.image_asset_id,
        audio_asset_id=payload.audio_asset_id,
        tags_json=json.dumps(_clean_tags(payload.tags), ensure_ascii=False),
        owner_id=owner_id,
        owner_name=owner_name,
        origin="local",
    )
    db.add(ca)
    db.commit()
    db.refresh(ca)
    return _to_response(ca, owner_id)


@router.get("/{ca_id}", response_model=CreationAssetResponse)
def get_creation_asset(ca_id: str, db: Session = Depends(get_db)) -> CreationAssetResponse:
    owner_id, _ = svc.get_or_create_owner(db)
    ca = db.get(CreationAsset, ca_id)
    if not ca:
        raise HTTPException(404, detail={"code": "not_found", "message": f"创作资产 {ca_id} 不存在"})
    return _to_response(ca, owner_id)


@router.patch("/{ca_id}", response_model=CreationAssetResponse)
def update_creation_asset(
    ca_id: str, payload: CreationAssetUpdate, db: Session = Depends(get_db)
) -> CreationAssetResponse:
    owner_id, _ = svc.get_or_create_owner(db)
    ca = db.get(CreationAsset, ca_id)
    if not ca:
        raise HTTPException(404, detail={"code": "not_found", "message": f"创作资产 {ca_id} 不存在"})

    if payload.image_asset_id is not None or payload.audio_asset_id is not None:
        _validate_media_refs(db, payload.image_asset_id, payload.audio_asset_id)
    old_image, old_audio = ca.image_asset_id, ca.audio_asset_id

    if payload.name is not None:
        ca.name = payload.name.strip()
    if payload.category is not None:
        ca.category = payload.category
    if payload.description is not None:
        ca.description = payload.description
    if payload.tags is not None:
        ca.tags_json = json.dumps(_clean_tags(payload.tags), ensure_ascii=False)
    if payload.image_asset_id is not None:
        ca.image_asset_id = payload.image_asset_id
    if payload.audio_asset_id is not None:
        ca.audio_asset_id = payload.audio_asset_id
    ca.updated_at = svc.now_iso()
    db.commit()
    db.refresh(ca)

    # 替换后清理不再被引用的旧媒体文件
    for old in (old_image, old_audio):
        if old and old not in (ca.image_asset_id, ca.audio_asset_id):
            svc.cleanup_media_asset(db, old, exclude_ca_id=ca.id)
    return _to_response(ca, owner_id)


@router.delete("/{ca_id}", response_model=MessageResponse)
def delete_creation_asset(ca_id: str, db: Session = Depends(get_db)) -> MessageResponse:
    owner_id, _ = svc.get_or_create_owner(db)
    ca = db.get(CreationAsset, ca_id)
    if not ca:
        raise HTTPException(404, detail={"code": "not_found", "message": f"创作资产 {ca_id} 不存在"})

    for media_id in (ca.image_asset_id, ca.audio_asset_id):
        svc.cleanup_media_asset(db, media_id, exclude_ca_id=ca.id)
    db.delete(ca)
    db.commit()
    return MessageResponse(message=f"创作资产 {ca_id} 已删除")


# ---------------- 同步 / 拉取 ----------------

@router.post("/sync", response_model=SyncResultResponse)
def sync_assets_by_tag(
    payload: TagSyncRequest, db: Session = Depends(get_db)
) -> SyncResultResponse:
    """将该标签（项目）下的资产上传到七牛云（乐观锁，绝不盲覆盖）。"""
    _require_qiniu()
    try:
        items = svc.sync_assets_by_tag(db, payload.tag)
    except ProviderError as e:
        raise HTTPException(400, detail={"code": "sync_failed", "message": str(e)})
    return SyncResultResponse(tag=payload.tag.strip(), items=items)


@router.post("/pull", response_model=SyncResultResponse)
def pull_assets_by_tag(
    payload: TagSyncRequest, db: Session = Depends(get_db)
) -> SyncResultResponse:
    """从七牛云拉取该标签（项目）下全部资产（三方合并，冲突保两份）。"""
    _require_qiniu()
    try:
        items = svc.pull_assets_by_tag(db, payload.tag)
    except ProviderError as e:
        raise HTTPException(400, detail={"code": "pull_failed", "message": str(e)})
    return SyncResultResponse(tag=payload.tag.strip(), items=items)


# ---------------- 内部工具 ----------------

def _clean_tags(tags: list[str]) -> list[str]:
    """去重、去空白，保持顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _validate_media_refs(db: Session, image_asset_id: str | None, audio_asset_id: str | None) -> None:
    """校验关联媒体 Asset 存在且为轻量类型（图片/音频，视频不同步）。"""
    for label, asset_id, allowed in (
        ("图片", image_asset_id, ("image/",)),
        ("音频", audio_asset_id, ("audio/",)),
    ):
        if not asset_id:
            continue
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(
                400,
                detail={
                    "code": "invalid_media_ref",
                    "message": f"{label}资产 {asset_id} 不存在，请先通过 /assets/upload 上传",
                },
            )
        mime = asset.mime_type or ""
        if not any(mime.startswith(p) for p in allowed):
            raise HTTPException(
                400,
                detail={
                    "code": "media_type_not_allowed",
                    "message": (
                        f"{label}资产 {asset_id} 的类型为 {mime or '未知'}，"
                        "素材库仅支持图片/音频轻量资产（视频不同步）"
                    ),
                },
            )
