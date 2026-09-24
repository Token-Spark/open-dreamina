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
import subprocess
import tempfile
import uuid
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ReviewItem, ReviewSession
from ..utils.file_utils import THUMBNAIL_WIDTH, detect_mime_type
from ..utils.time_utils import now_iso as _now_iso

# 支持审阅的文件扩展名（按类型分组）
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac"}
_SCANNABLE_EXTS = _IMAGE_EXTS | _VIDEO_EXTS | _AUDIO_EXTS

# 缩略图存放根目录（相对 assets_dir 同级）
_THUMB_DIR_NAME = "review_thumbs"


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _thumb_base_path() -> Path:
    """缩略图根目录：与 assets 目录同级的 review_thumbs/。

    审阅缩略图属于本实例生成的数据（非外部素材），统一落在数据根目录下，
    便于备份与清理；不依赖数据库文件位置。
    """
    p = settings.assets_path.parent / _THUMB_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _guess_asset_type(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "image"


def _probe_media_meta(abs_path: Path, mime_type: str) -> tuple[int | None, int | None, float | None]:
    """探测图片宽高 / 视频宽高+时长。"""
    width = height = None
    duration: float | None = None
    asset_type = _guess_asset_type(mime_type)
    if asset_type == "image":
        try:
            with Image.open(abs_path) as img:
                width, height = img.size
        except Exception:
            pass
    elif asset_type == "video":
        try:
            from ..utils.file_utils import _probe_video_meta
            width, height, duration = _probe_video_meta(abs_path)
        except Exception:
            pass
    return width, height, duration


def _generate_review_thumbnail(
    abs_path: Path, session_id: str, mime_type: str
) -> str | None:
    """为审阅文件生成缩略图，返回相对 _thumb_base_path 的路径。

    与资产缩略图不同：外部素材目录可能只读、且不应被写入，
    因此缩略图一律生成到 data/review_thumbs/{session_id}/ 下，
    不在源文件所在目录留下任何文件。
    """
    asset_type = _guess_asset_type(mime_type)
    if asset_type == "audio":
        return None  # 音频无缩略图
    try:
        dest_dir = _thumb_base_path() / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{uuid.uuid4().hex}_thumb.webp"

        if asset_type == "video":
            if not _write_video_thumbnail(abs_path, dest):
                return None
        else:
            with Image.open(abs_path) as img:
                _save_webp_thumbnail(img, dest)

        return str(dest.relative_to(_thumb_base_path())).replace("\\", "/")
    except Exception:
        return None


def _save_webp_thumbnail(img: "Image.Image", dest: Path) -> None:
    """等比缩放并保存为 WebP 缩略图。"""
    img = img.convert("RGB")
    if img.width <= 0:
        raise ValueError("图片宽度为 0")
    ratio = THUMBNAIL_WIDTH / img.width
    new_size = (THUMBNAIL_WIDTH, max(1, int(img.height * ratio)))
    img.resize(new_size, Image.LANCZOS).save(dest, format="WEBP", quality=85)


def _write_video_thumbnail(source_abs: Path, dest: Path) -> bool:
    """用 ffmpeg 抽第一帧生成 WebP 缩略图。

    抽帧产物写入系统临时目录，避免污染外部素材目录（可能是只读挂载）。
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            frame_path = Path(tmp) / "frame.png"
            cmd = [
                "ffmpeg", "-y", "-i", str(source_abs),
                "-frames:v", "1", "-q:v", "2",
                str(frame_path),
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0 or not frame_path.exists():
                return False
            with Image.open(frame_path) as img:
                _save_webp_thumbnail(img, dest)
        return True
    except Exception:
        return False


def _resolve_thumbnail_path(thumb_rel: str | None) -> Path | None:
    """将 review_thumbs 下的相对路径解析为绝对路径。"""
    if not thumb_rel:
        return None
    p = _thumb_base_path() / thumb_rel
    return p if p.exists() else None


def _delete_thumbnail_file(thumb_rel: str | None) -> None:
    """删除缩略图文件（若存在）。失败静默忽略，不阻断扫描。"""
    if not thumb_rel:
        return
    try:
        p = _thumb_base_path() / thumb_rel
        if p.is_file():
            p.unlink()
    except OSError:
        pass


# ---------------- 路径安全验证 ----------------

def _is_path_allowed(folder_path: str) -> Path:
    """验证文件夹路径是否在配置允许的根目录下，返回解析后的绝对路径。

    安全要求：防止路径遍历攻击，只允许访问配置的根目录下的子目录。
    resolve() 会展开符号链接，因此指向外部的软链接同样会被拒绝。
    """
    requested = Path(folder_path).expanduser().resolve()
    for root in settings.review_source_paths:
        if not _is_within(requested, root):
            continue
        if not requested.is_dir():
            raise ValueError(f"路径不是目录或不存在: {requested}")
        return requested
    raise ValueError(
        f"路径不在允许的审阅目录内: {folder_path}。"
        f"请在 .env 中配置 REVIEW_SOURCE_ROOTS 指向素材所在目录。"
    )


def _is_within(path: Path, root: Path) -> bool:
    """判断 path 是否等于 root 或位于 root 之下（不区分大小写由 Path 处理）。"""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def list_review_folders() -> list[dict]:
    """列出所有允许根目录及其下的子文件夹（递归两层），供前端选择审阅目标。

    返回格式：[{path, name, subdirs: [{path, name, subdirs: [{path, name}]}]}]
    """
    result: list[dict] = []
    for root in settings.review_source_paths:
        if not root.exists():
            result.append({"path": str(root), "name": root.name, "subdirs": [], "exists": False})
            continue
        subdirs: list[dict] = []
        try:
            for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                # 第二层子目录
                level2: list[dict] = []
                try:
                    for grandchild in sorted(child.iterdir(), key=lambda p: p.name.lower()):
                        if grandchild.is_dir() and not grandchild.name.startswith("."):
                            level2.append({"path": str(grandchild), "name": grandchild.name})
                except PermissionError:
                    pass
                subdirs.append({"path": str(child), "name": child.name, "subdirs": level2})
        except PermissionError:
            pass
        result.append({
            "path": str(root),
            "name": root.name,
            "subdirs": subdirs,
            "exists": True,
        })
    return result


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
