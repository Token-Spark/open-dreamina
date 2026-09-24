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

"""制片人审阅路由：会话 CRUD + 条目列表/更新/批量更新 + 文件夹浏览。

安全设计：
- folder_path 必须在 REVIEW_SOURCE_ROOTS 配置允许的根目录下（service 层验证）；
- 文件与缩略图通过流式响应返回，不暴露绝对路径。
"""
from __future__ import annotations

import json
import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ReviewItem, ReviewSession
from ..schemas import (
    ReviewBatchUpdateRequest,
    ReviewBatchUpdateResponse,
    ReviewFolderListResponse,
    ReviewItemResponse,
    ReviewItemUpdate,
    ReviewScanResponse,
    ReviewSessionCreate,
    ReviewSessionListResponse,
    ReviewSessionResponse,
    ReviewSessionUpdate,
)
from ..services.review_service import (
    batch_update_items,
    compute_summary,
    create_session,
    delete_session,
    get_item,
    get_session,
    list_review_folders,
    list_sessions,
    resolve_item_file,
    scan_folder,
    update_item,
    update_session,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])


# ---------------- 会话 ----------------

def _session_to_response(session: ReviewSession) -> ReviewSessionResponse:
    summary = json.loads(session.summary_json or "{}")
    if not summary:
        summary = compute_summary(session)
    return ReviewSessionResponse(
        id=session.id,
        title=session.title,
        folder_path=session.folder_path,
        status=session.status,
        summary=summary,
        item_count=len(session.items),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _item_to_response(item: ReviewItem) -> ReviewItemResponse:
    return ReviewItemResponse(
        id=item.id,
        session_id=item.session_id,
        file_path=item.file_path,
        file_name=item.file_name,
        file_size=item.file_size,
        mime_type=item.mime_type,
        width=item.width,
        height=item.height,
        duration=item.duration,
        thumbnail_path=item.thumbnail_path,
        status=item.status,
        feedback=item.feedback,
        sort_order=item.sort_order,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        thumbnail_url=f"/api/v1/reviews/items/{item.id}/thumbnail" if item.thumbnail_path else None,
        file_url=f"/api/v1/reviews/items/{item.id}/file",
    )


@router.get("/folders", response_model=ReviewFolderListResponse)
def get_review_folders() -> ReviewFolderListResponse:
    """列出允许根目录下的可选子文件夹，供前端选择审阅目标。"""
    return ReviewFolderListResponse(roots=list_review_folders())


@router.get("/sessions", response_model=ReviewSessionListResponse)
def list_review_sessions(db: Session = Depends(get_db)) -> ReviewSessionListResponse:
    sessions = list_sessions(db)
    return ReviewSessionListResponse(
        items=[_session_to_response(s) for s in sessions],
        total=len(sessions),
    )


@router.post("/sessions", response_model=ReviewSessionResponse, status_code=201)
def create_review_session(
    payload: ReviewSessionCreate,
    db: Session = Depends(get_db),
) -> ReviewSessionResponse:
    try:
        session = create_session(db, payload.title, payload.folder_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "invalid_folder", "message": str(e)})
    db.refresh(session)
    return _session_to_response(session)


@router.get("/sessions/{session_id}", response_model=ReviewSessionResponse)
def get_review_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ReviewSessionResponse:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅会话 {session_id} 不存在"})
    return _session_to_response(session)


@router.patch("/sessions/{session_id}", response_model=ReviewSessionResponse)
def update_review_session(
    session_id: str,
    payload: ReviewSessionUpdate,
    db: Session = Depends(get_db),
) -> ReviewSessionResponse:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅会话 {session_id} 不存在"})
    if payload.title is None and payload.status is None:
        raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": "至少需要传入 title 或 status"})
    session = update_session(db, session, payload.title, payload.status)
    return _session_to_response(session)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_review_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> None:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅会话 {session_id} 不存在"})
    delete_session(db, session)


@router.post("/sessions/{session_id}/scan", response_model=ReviewScanResponse)
def rescan_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> ReviewScanResponse:
    """重新扫描文件夹，同步新增/移除的文件。"""
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅会话 {session_id} 不存在"})
    try:
        result = scan_folder(db, session, session.folder_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "scan_failed", "message": str(e)})
    return ReviewScanResponse(**result)


# ---------------- 条目 ----------------

@router.get("/sessions/{session_id}/items", response_model=list[ReviewItemResponse])
def list_review_items(
    session_id: str,
    status: str | None = Query(None, description="按状态过滤：pending|approved|rejected|needs_revision"),
    db: Session = Depends(get_db),
) -> list[ReviewItemResponse]:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅会话 {session_id} 不存在"})
    items = sorted(session.items, key=lambda i: i.sort_order)
    if status:
        items = [i for i in items if i.status == status]
    return [_item_to_response(i) for i in items]


@router.patch("/items/{item_id}", response_model=ReviewItemResponse)
def update_review_item(
    item_id: str,
    payload: ReviewItemUpdate,
    db: Session = Depends(get_db),
) -> ReviewItemResponse:
    item = get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅条目 {item_id} 不存在"})
    item = update_item(db, item, payload.status, payload.feedback)
    return _item_to_response(item)


@router.post("/sessions/{session_id}/items/batch", response_model=ReviewBatchUpdateResponse)
def batch_update_review_items(
    session_id: str,
    payload: ReviewBatchUpdateRequest,
    db: Session = Depends(get_db),
) -> ReviewBatchUpdateResponse:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅会话 {session_id} 不存在"})
    updates = [
        {"id": u.id, "status": u.status, "feedback": u.feedback}
        for u in payload.items
    ]
    updated, failed = batch_update_items(db, session_id, updates)
    return ReviewBatchUpdateResponse(updated=updated, failed=failed)


# ---------------- 文件 / 缩略图流式响应 ----------------

@router.get("/items/{item_id}/file")
def get_review_item_file(item_id: str, db: Session = Depends(get_db)):
    item = get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅条目 {item_id} 不存在"})
    path = resolve_item_file(item)
    if not path:
        raise HTTPException(status_code=404, detail={"code": "file_missing", "message": "源文件不存在"})
    media_type = item.mime_type or (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return FileResponse(path=path, media_type=media_type, filename=path.name)


@router.get("/items/{item_id}/thumbnail")
def get_review_item_thumbnail(item_id: str, db: Session = Depends(get_db)):
    item = get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"审阅条目 {item_id} 不存在"})
    if not item.thumbnail_path:
        raise HTTPException(status_code=404, detail={"code": "no_thumbnail", "message": "该条目无缩略图"})
    from ..services.review_service import _resolve_thumbnail_path
    path = _resolve_thumbnail_path(item.thumbnail_path)
    if not path:
        raise HTTPException(status_code=404, detail={"code": "file_missing", "message": "缩略图文件不存在"})
    return FileResponse(path=path, media_type="image/webp")
