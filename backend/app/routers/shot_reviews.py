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

"""剧集镜头审片路由：会话 CRUD + 条目评分/意见 + 扫描 + 视频流式响应。

与制片人审阅（reviews）共用相同的路径安全与缩略图能力；
差异在于按「集 → 镜」组织、以 0–100 评分代替状态标记，
并支持同镜号多版本「选定保留版本」与废弃视频删除。
"""
from __future__ import annotations

import json
import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import ShotReviewItem, ShotReviewSession
from ..schemas_shot_review import (
    ShotReviewBatchUpdateRequest,
    ShotReviewBatchUpdateResponse,
    ShotReviewBulkDeleteRequest,
    ShotReviewBulkDeleteResponse,
    ShotReviewFolderListResponse,
    ShotReviewItemResponse,
    ShotReviewItemUpdate,
    ShotReviewScanResponse,
    ShotReviewSessionCreate,
    ShotReviewSessionListResponse,
    ShotReviewSessionResponse,
    ShotReviewSessionUpdate,
)
from ..services.review_service import list_review_folders
from ..services.shot_review_service import (
    batch_update_items,
    bulk_delete_items,
    compute_summary,
    create_session,
    delete_item,
    delete_session,
    ensure_thumbnail,
    get_item,
    get_session,
    list_sessions,
    resolve_item_file,
    scan_root,
    update_item,
    update_session,
    verdict_for_score,
)

router = APIRouter(prefix="/shot-reviews", tags=["shot-reviews"])


def _session_to_response(session: ShotReviewSession) -> ShotReviewSessionResponse:
    summary = json.loads(session.summary_json or "{}")
    if not summary:
        summary = compute_summary(session)
    return ShotReviewSessionResponse(
        id=session.id,
        title=session.title,
        root_path=session.root_path,
        status=session.status,
        summary=summary,
        item_count=len(session.items),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _item_to_response(item: ShotReviewItem) -> ShotReviewItemResponse:
    return ShotReviewItemResponse(
        id=item.id,
        session_id=item.session_id,
        episode=item.episode,
        shot_id=item.shot_id,
        file_path=item.file_path,
        file_name=item.file_name,
        file_size=item.file_size,
        mime_type=item.mime_type,
        width=item.width,
        height=item.height,
        duration=item.duration,
        thumbnail_path=item.thumbnail_path,
        score=item.score,
        verdict=verdict_for_score(item.score),
        feedback=item.feedback,
        selected=item.selected,
        source_prompt=item.source_prompt,
        revised_prompt=item.revised_prompt,
        shot_function=item.shot_function,
        script_duration=item.script_duration,
        shot_size=item.shot_size,
        movement=item.movement,
        dialogue=item.dialogue,
        render_status=item.render_status,
        model=item.model,
        sort_order=item.sort_order,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        # 缩略图按需生成，扫描时未知是否有，故始终暴露该地址（前端首屏可视区域才会请求）
        thumbnail_url=f"/api/v1/shot-reviews/items/{item.id}/thumbnail",
        file_url=f"/api/v1/shot-reviews/items/{item.id}/file",
    )


# ---------------- 会话 ----------------

@router.get("/folders", response_model=ShotReviewFolderListResponse)
def get_shot_review_folders() -> ShotReviewFolderListResponse:
    """列出镜头审片可写根目录下的可选子文件夹（与制片人审阅的目录配置相互独立，默认相同）。"""
    return ShotReviewFolderListResponse(
        roots=list_review_folders(roots=settings.shot_review_source_paths)
    )


@router.get("/sessions", response_model=ShotReviewSessionListResponse)
def list_shot_review_sessions(db: Session = Depends(get_db)) -> ShotReviewSessionListResponse:
    sessions = list_sessions(db)
    return ShotReviewSessionListResponse(
        items=[_session_to_response(s) for s in sessions],
        total=len(sessions),
    )


@router.post("/sessions", response_model=ShotReviewSessionResponse, status_code=201)
def create_shot_review_session(
    payload: ShotReviewSessionCreate,
    db: Session = Depends(get_db),
) -> ShotReviewSessionResponse:
    try:
        session = create_session(db, payload.title, payload.root_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "invalid_folder", "message": str(e)})
    db.refresh(session)
    return _session_to_response(session)


@router.get("/sessions/{session_id}", response_model=ShotReviewSessionResponse)
def get_shot_review_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ShotReviewSessionResponse:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片会话 {session_id} 不存在"})
    return _session_to_response(session)


@router.patch("/sessions/{session_id}", response_model=ShotReviewSessionResponse)
def update_shot_review_session(
    session_id: str,
    payload: ShotReviewSessionUpdate,
    db: Session = Depends(get_db),
) -> ShotReviewSessionResponse:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片会话 {session_id} 不存在"})
    if payload.title is None and payload.status is None:
        raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": "至少需要传入 title 或 status"})
    session = update_session(db, session, payload.title, payload.status)
    return _session_to_response(session)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_shot_review_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> None:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片会话 {session_id} 不存在"})
    delete_session(db, session)


@router.post("/sessions/{session_id}/scan", response_model=ShotReviewScanResponse)
def rescan_shot_review_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ShotReviewScanResponse:
    """重新扫描根目录，同步新增/移除的镜头视频。"""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片会话 {session_id} 不存在"})
    try:
        result = scan_root(db, session, session.root_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "scan_failed", "message": str(e)})
    return ShotReviewScanResponse(**result)


# ---------------- 条目 ----------------

@router.get("/sessions/{session_id}/items", response_model=list[ShotReviewItemResponse])
def list_shot_review_items(
    session_id: str,
    episode: str | None = Query(None, description="按集号过滤，如 EP05"),
    verdict: str | None = Query(None, description="按档位过滤：pending|pass|revise|redesign"),
    db: Session = Depends(get_db),
) -> list[ShotReviewItemResponse]:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片会话 {session_id} 不存在"})
    items = sorted(session.items, key=lambda i: i.sort_order)
    if episode:
        items = [i for i in items if (i.episode or "").upper() == episode.upper()]
    if verdict:
        items = [i for i in items if verdict_for_score(i.score) == verdict]
    return [_item_to_response(i) for i in items]


@router.patch("/items/{item_id}", response_model=ShotReviewItemResponse)
def update_shot_review_item(
    item_id: str,
    payload: ShotReviewItemUpdate,
    db: Session = Depends(get_db),
) -> ShotReviewItemResponse:
    item = get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片条目 {item_id} 不存在"})
    item = update_item(
        db, item, payload.score, payload.clear_score, payload.feedback,
        payload.revised_prompt, payload.selected,
    )
    return _item_to_response(item)


@router.post("/sessions/{session_id}/items/batch", response_model=ShotReviewBatchUpdateResponse)
def batch_update_shot_review_items(
    session_id: str,
    payload: ShotReviewBatchUpdateRequest,
    db: Session = Depends(get_db),
) -> ShotReviewBatchUpdateResponse:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片会话 {session_id} 不存在"})
    updates = [
        {
            "id": u.id,
            "score": u.score,
            "clear_score": u.clear_score,
            "feedback": u.feedback,
            "revised_prompt": u.revised_prompt,
            "selected": u.selected,
        }
        for u in payload.items
    ]
    updated, failed = batch_update_items(db, session_id, updates)
    return ShotReviewBatchUpdateResponse(updated=updated, failed=failed)


@router.post("/sessions/{session_id}/items/delete", response_model=ShotReviewBulkDeleteResponse)
def bulk_delete_shot_review_items(
    session_id: str,
    payload: ShotReviewBulkDeleteRequest,
    db: Session = Depends(get_db),
) -> ShotReviewBulkDeleteResponse:
    """批量删除审片条目，用于清理同镜号下未选定的废弃版本。

    delete_file=True 时同时从磁盘删除视频文件（路径经允许根目录双重校验），
    外部素材目录必须以可写方式挂载，否则逐条返回删除失败原因。
    """
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片会话 {session_id} 不存在"})
    try:
        result = bulk_delete_items(db, session, payload.item_ids, payload.delete_file)
    except (ValueError, PermissionError, OSError) as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "delete_failed", "message": f"删除视频文件失败：{e}。若目录以只读方式挂载，请在宿主机手动删除后重新扫描。"},
        )
    return ShotReviewBulkDeleteResponse(**result)


@router.delete("/items/{item_id}", response_model=ShotReviewBulkDeleteResponse)
def delete_shot_review_item(
    item_id: str,
    delete_file: bool = Query(False, description="是否同时从磁盘删除视频文件；False 仅移出审片列表"),
    db: Session = Depends(get_db),
) -> ShotReviewBulkDeleteResponse:
    item = get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片条目 {item_id} 不存在"})
    try:
        result = delete_item(db, item, delete_file)
    except (ValueError, PermissionError, OSError) as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "delete_failed", "message": f"删除视频文件失败：{e}。若目录以只读方式挂载，请在宿主机手动删除后重新扫描。"},
        )
    return ShotReviewBulkDeleteResponse(**result)


# ---------------- 视频 / 缩略图流式响应 ----------------

@router.get("/items/{item_id}/file")
def get_shot_review_item_file(item_id: str, db: Session = Depends(get_db)):
    item = get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片条目 {item_id} 不存在"})
    path = resolve_item_file(item)
    if not path:
        raise HTTPException(status_code=404, detail={"code": "file_missing", "message": "源视频不存在"})
    media_type = item.mime_type or (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return FileResponse(path=path, media_type=media_type, filename=path.name)


@router.get("/items/{item_id}/thumbnail")
def get_shot_review_item_thumbnail(item_id: str, db: Session = Depends(get_db)):
    """返回镜头视频首帧缩略图；首次访问时才用 ffmpeg 抽帧并缓存。"""
    item = get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审片条目 {item_id} 不存在"})
    path = ensure_thumbnail(db, item)
    if not path:
        raise HTTPException(status_code=404, detail={"code": "no_thumbnail", "message": "该条目无缩略图"})
    return FileResponse(path=path, media_type="image/webp")