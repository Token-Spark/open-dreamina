# Copyright 2026 Open Dreamina Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""制片人审阅业务服务。

负责：
- 验证外部文件夹路径是否在配置允许的根目录下；
- 扫描文件夹中的图片/视频文件，生成缩略图并写入 ReviewItem 记录；
- 审阅会话与条目的 CRUD；
- 批量更新审阅状态与修改意见；
- 汇总统计（各状态计数）。

缩略图存放在 data/review_thumbs/ 目录下，以会话 id 为子目录。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import ReviewItem, ReviewSession
from ..utils.file_utils import detect_mime_type
from ..utils.time_utils import now_iso as _now_iso
from .review_common import (
    delete_thumbnail_file as _delete_thumbnail_file,
    generate_review_thumbnail as _generate_review_thumbnail,
    guess_asset_type as _guess_asset_type,
    is_path_allowed as _is_path_allowed,
    is_shot_path_allowed,
    is_within as _is_within,
    list_review_folders,
    probe_media_meta as _probe_media_meta,
    resolve_thumbnail_path as _resolve_thumbnail_path,
    thumb_base_path as _thumb_base_path,
)

# 支持审阅的文件扩展名（按类型分组）
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac"}
_SCANNABLE_EXTS = _IMAGE_EXTS | _VIDEO_EXTS | _AUDIO_EXTS



def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------- 扫描 ----------------

# 扩展名已知时仍传入前 1KB 即可满足魔术字节嗅探，避免整文件读入
_HEAD_BYTES = 1024


def _read_head_bytes(abs_file: Path) -> bytes:
    """读取文件头部若干字节用于 MIME 嗅探（避免整文件读入）。"""
    try:
        with abs_file.open("rb") as fh:
            return fh.read(_HEAD_BYTES)
    except OSError:
        return b""


def scan_folder(
    db: Session, session: ReviewSession, folder_path: str
) -> dict:
    """扫描文件夹（递归子目录），新增未记录的文件、移除已不存在的文件。

    相对路径保留子目录层级（如 ``01_characters/zeus/ZEUS_PRIMARY.png``），
    便于前端按类别分组展示。
    """
    abs_folder = _is_path_allowed(folder_path)

    # 收集现有条目的相对路径
    existing: dict[str, ReviewItem] = {
        item.file_path: item for item in session.items
    }

    # 递归扫描目录下的所有支持文件
    found_files: dict[str, Path] = {}
    try:
        for child in sorted(abs_folder.rglob("*"), key=lambda p: str(p.relative_to(abs_folder)).lower()):
            if not child.is_file():
                continue
            if child.suffix.lower() not in _SCANNABLE_EXTS:
                continue
            # 相对路径保留子目录层级（用正斜杠统一跨平台）
            rel = str(child.relative_to(abs_folder)).replace("\\", "/")
            found_files[rel] = child
    except PermissionError:
        raise ValueError(f"无权限访问目录: {abs_folder}")

    added = 0
    removed = 0

    # 新增
    sort_idx = len(existing)
    for rel_name, abs_file in found_files.items():
        if rel_name in existing:
            continue
        file_size = abs_file.stat().st_size
        # detect_mime_type 优先按扩展名查表，命中时无需读文件内容；
        # 仅在扩展名未知时才读入（并限制大小）做魔术字节嗅探。
        mime_type = detect_mime_type(abs_file.name, _read_head_bytes(abs_file))
        width, height, duration = _probe_media_meta(abs_file, mime_type)
        thumb_rel = _generate_review_thumbnail(abs_file, session.id, mime_type)

        item = ReviewItem(
            id=_new_uuid(),
            session_id=session.id,
            file_path=rel_name,
            file_name=abs_file.name,
            file_size=file_size,
            mime_type=mime_type,
            width=width,
            height=height,
            duration=duration,
            thumbnail_path=thumb_rel,
            status="pending",
            feedback="",
            sort_order=sort_idx,
        )
        db.add(item)
        session.items.append(item)
        sort_idx += 1
        added += 1

    # 移除已不存在的文件（连同其缩略图，避免残留孤儿文件）
    for rel_name, item in existing.items():
        if rel_name not in found_files:
            _delete_thumbnail_file(item.thumbnail_path)
            db.delete(item)
            removed += 1

    session.updated_at = _now_iso()
    db.commit()
    recompute_summary(db, session)

    return {"added": added, "removed": removed, "total": len(session.items)}


# ---------------- 汇总 ----------------

def compute_summary(session: ReviewSession) -> dict:
    """计算会话的汇总统计。"""
    counts: dict[str, int] = {
        "pending": 0,
        "approved": 0,
        "rejected": 0,
        "needs_revision": 0,
    }
    total = 0
    for item in session.items:
        total += 1
        counts[item.status] = counts.get(item.status, 0) + 1
    counts["total"] = total
    counts["reviewed"] = counts["approved"] + counts["rejected"] + counts["needs_revision"]
    return counts


def recompute_summary(db: Session, session: ReviewSession) -> dict:
    summary = compute_summary(session)
    session.summary_json = json.dumps(summary, ensure_ascii=False)
    session.updated_at = _now_iso()
    db.commit()
    return summary


# ---------------- CRUD ----------------

def create_session(
    db: Session, title: str, folder_path: str
) -> ReviewSession:
    """创建审阅会话并立即扫描文件夹。"""
    abs_folder = _is_path_allowed(folder_path)
    session = ReviewSession(
        id=_new_uuid(),
        title=title,
        folder_path=str(abs_folder),
        status="in_review",
        summary_json="{}",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 扫描文件夹
    scan_folder(db, session, str(abs_folder))
    return session


def get_session(db: Session, session_id: str) -> ReviewSession | None:
    return db.get(ReviewSession, session_id)


def list_sessions(db: Session) -> list[ReviewSession]:
    from sqlalchemy import desc
    return db.query(ReviewSession).order_by(desc(ReviewSession.updated_at)).all()


def update_session(
    db: Session, session: ReviewSession, title: str | None, status: str | None
) -> ReviewSession:
    if title is not None:
        session.title = title
    if status is not None:
        session.status = status
    session.updated_at = _now_iso()
    db.commit()
    db.refresh(session)
    return session


def delete_session(db: Session, session: ReviewSession) -> None:
    # 删除缩略图文件
    thumb_dir = _thumb_base_path() / session.id
    if thumb_dir.exists():
        import shutil
        try:
            shutil.rmtree(str(thumb_dir))
        except Exception:
            pass
    db.delete(session)
    db.commit()


def get_item(db: Session, item_id: str) -> ReviewItem | None:
    return db.get(ReviewItem, item_id)


def update_item(
    db: Session,
    item: ReviewItem,
    status: str | None,
    feedback: str | None,
) -> ReviewItem:
    if status is not None:
        item.status = status
    if feedback is not None:
        item.feedback = feedback
    if status is not None or feedback is not None:
        item.reviewed_at = _now_iso()
    item.updated_at = _now_iso()
    db.commit()
    db.refresh(item)
    # 重新计算会话汇总
    session = item.session
    if session:
        recompute_summary(db, session)
    return item


def batch_update_items(
    db: Session, session_id: str, updates: list[dict]
) -> tuple[int, int]:
    """批量更新审阅条目。updates: [{id, status?, feedback?}]"""
    updated = 0
    failed = 0
    session_items: dict[str, ReviewItem] = {}
    session = db.get(ReviewSession, session_id)
    if session:
        session_items = {item.id: item for item in session.items}

    for upd in updates:
        item = session_items.get(upd["id"])
        if not item:
            failed += 1
            continue
        changed = False
        if upd.get("status") is not None:
            item.status = upd["status"]
            changed = True
        if upd.get("feedback") is not None:
            item.feedback = upd["feedback"]
            changed = True
        if changed:
            item.reviewed_at = _now_iso()
            item.updated_at = _now_iso()
            updated += 1
    db.commit()
    if session:
        recompute_summary(db, session)
    return updated, failed


def resolve_item_file(item: ReviewItem) -> Path | None:
    """解析审阅条目对应的外部文件绝对路径。

    file_path 是相对会话 folder_path 的路径（可能含子目录层级）。
    """
    session = item.session
    if not session:
        return None
    p = Path(session.folder_path) / item.file_path
    return p if p.exists() else None
