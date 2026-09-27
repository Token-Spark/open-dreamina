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

"""剧集镜头审片业务服务。

负责：
- 扫描剧集视频根目录（如 分镜脚本/），递归收集镜头视频；
- 从相对路径与文件名解析集号/镜号，并关联同集 shots.md 与生成报告的分镜信息；
- 生成缩略图（复用制片人审阅的 ffmpeg 抽帧能力，落在 data/review_thumbs/ 下）；
- 打分（0–100）、修改意见、精修提示词的读写，以及按评分档位的汇总统计；
- 同镜号多版本管理：为同一栏目内的视频标记「选定保留版本」（组内互斥），
  并支持删除废弃版本条目及对应视频文件（路径经允许根目录双重校验）。

评分档位（对齐 ai-video-director 规范，由 score 派生，不落库）：
  ≥70 通过（pass）｜60–69 需重生成（revise）｜<60 需重新设计（redesign）｜未打分 待审（pending）。
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import ShotReviewItem, ShotReviewSession
from ..utils.file_utils import detect_mime_type
from ..utils.time_utils import now_iso as _now_iso
from .review_service import (
    _delete_thumbnail_file,
    _generate_review_thumbnail,
    _is_within,
    _probe_media_meta,
    _resolve_thumbnail_path,
    _thumb_base_path,
    is_shot_path_allowed,
)
from .shot_script_meta import (
    EPISODE_DIR_RE,
    find_episode_dir,
    load_episode_meta,
    locate_script_dir,
    parse_shot_key,
)

# 镜头审片只面向成片视频
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".flv"}

# 评分档位阈值
PASS_SCORE = 70
REVISE_SCORE = 60

_HEAD_BYTES = 1024
_ANCESTOR_PARTS = 6


def _new_uuid() -> str:
    return str(uuid.uuid4())


def verdict_for_score(score: int | None) -> str:
    """评分 → 档位：pass / revise / redesign / pending。"""
    if score is None:
        return "pending"
    if score >= PASS_SCORE:
        return "pass"
    if score >= REVISE_SCORE:
        return "revise"
    return "redesign"


# ---------------- 扫描 ----------------

def _read_head_bytes(abs_file: Path) -> bytes:
    try:
        with abs_file.open("rb") as fh:
            return fh.read(_HEAD_BYTES)
    except OSError:
        return b""


def _collect_videos(abs_root: Path) -> dict[str, Path]:
    """递归收集根目录下的视频文件，键为相对根目录的 posix 路径。

    跳过以 ``_`` 开头的目录：本项目中 ``_superseded_*``（被淘汰的历史版本）与
    ``_model_compare``（模型对比产物）属于辅助产物，混入审片列表会与当前交付版本
    在同一镜号下重复出现，干扰打分。
    """
    found: dict[str, Path] = {}
    for child in abs_root.rglob("*"):
        if not child.is_file() or child.suffix.lower() not in _VIDEO_EXTS:
            continue
        rel = child.relative_to(abs_root)
        if any(part.startswith("_") for part in rel.parts[:-1]):
            continue
        found[str(rel).replace("\\", "/")] = child
    return found


def _resolve_identity(rel: str, abs_root: Path, meta_cache: dict[Path, dict]) -> tuple[str | None, str | None, str, dict]:
    """解析 (episode, shot_no, shot_id, 分镜元信息)。

    集号优先取路径中的 EPxx 目录，其次取文件名前缀；镜号取文件名/路径中的 Sxx。
    找不到镜号的视频仍可审片，镜号回落为 S?? 并如实不关联分镜信息。
    """
    parts = rel.split("/")
    abs_file = abs_root / rel
    file_episode, file_shot = parse_shot_key(abs_file.name)
    episode = find_episode_dir(parts) or file_episode

    script_dir = locate_script_dir(abs_file, abs_root)
    if episode is None and script_dir is not None and EPISODE_DIR_RE.match(script_dir.name):
        episode = script_dir.name.upper()

    shot_no = file_shot or parse_shot_key(*parts)[1]
    shot_id = f"{episode}-{shot_no}" if episode and shot_no else (shot_no or "S??")

    meta: dict = {}
    if script_dir is not None and shot_no:
        if script_dir not in meta_cache:
            meta_cache[script_dir] = load_episode_meta(script_dir)
        meta = meta_cache[script_dir].get(shot_no, {})
    return episode, shot_no, shot_id, meta


def _build_item(session_id: str, abs_root: Path, rel: str, meta_cache: dict[Path, dict]) -> ShotReviewItem:
    abs_file = abs_root / rel
    episode, _, shot_id, meta = _resolve_identity(rel, abs_root, meta_cache)
    mime_type = detect_mime_type(abs_file.name, _read_head_bytes(abs_file))
    width, height, duration = _probe_media_meta(abs_file, mime_type)
    # ffprobe 不可用时回落到生成报告中的实测时长，保证「应有 vs 实际」仍可对照
    if duration is None:
        duration = meta.get("render_duration_s")
    # 缩略图不在此处生成：整批 40 集可达数百个视频，逐个抽帧会让扫描请求阻塞数分钟。
    # 改为首次访问 /thumbnail 时按需生成并回写，见 ensure_thumbnail。
    thumb_rel = None

    return ShotReviewItem(
        id=_new_uuid(),
        session_id=session_id,
        episode=episode,
        shot_id=shot_id,
        file_path=rel,
        file_name=abs_file.name,
        file_size=abs_file.stat().st_size,
        mime_type=mime_type,
        width=width,
        height=height,
        duration=duration,
        thumbnail_path=thumb_rel,
        score=None,
        feedback="",
        shot_function=meta.get("shot_function"),
        script_duration=meta.get("script_duration"),
        shot_size=meta.get("shot_size"),
        movement=meta.get("movement"),
        dialogue=meta.get("dialogue"),
        source_prompt=meta.get("prompt_source"),
        render_status=meta.get("render_status"),
        model=meta.get("model"),
        sort_order=0,
    )


def _sort_key(item: ShotReviewItem) -> tuple:
    """集号 → 镜号 → 文件名，保证审片顺序与分镜一致。"""
    return (item.episode or "~", item.shot_id, item.file_name)


def _group_key(item: ShotReviewItem) -> tuple[str, str]:
    """多版本分组的键：同一集 + 同一镜号的视频归入同一栏目。"""
    return (item.episode or "", item.shot_id)


def scan_root(db: Session, session: ShotReviewSession, root_path: str) -> dict:
    """扫描根目录（递归），新增未记录的镜头视频、移除已不存在的条目。"""
    abs_root = is_shot_path_allowed(root_path)
    existing = {item.file_path: item for item in session.items}
    try:
        found = _collect_videos(abs_root)
    except PermissionError:
        raise ValueError(f"无权限访问目录: {abs_root}")

    meta_cache: dict[Path, dict] = {}
    added = 0
    for rel in sorted(found, key=str.lower):
        if rel in existing:
            continue
        item = _build_item(session.id, abs_root, rel, meta_cache)
        db.add(item)
        session.items.append(item)
        added += 1

    removed = 0
    backfilled = 0
    for rel, item in existing.items():
        if rel not in found:
            _delete_thumbnail_file(item.thumbnail_path)
            db.delete(item)
            removed += 1
            continue
        # 旧条目回填提示词底稿（扫描提取能力后补上线时），不触碰审阅结果
        if not item.source_prompt:
            _, _, _, meta = _resolve_identity(rel, abs_root, meta_cache)
            source = meta.get("prompt_source")
            if source:
                item.source_prompt = source
                backfilled += 1
    if backfilled:
        db.flush()

    _reindex(db, session)
    session.updated_at = _now_iso()
    db.commit()
    recompute_summary(db, session)
    return {"added": added, "removed": removed, "total": len(session.items)}


def _reindex(db: Session, session: ShotReviewSession) -> None:
    db.flush()
    for order, item in enumerate(sorted(session.items, key=_sort_key)):
        item.sort_order = order


# ---------------- 汇总 ----------------

def compute_summary(session: ShotReviewSession) -> dict:
    """按评分档位统计，并给出已评分数与平均分。

    另统计多版本镜头（同镜号 ≥2 个视频）与已选定保留版本的镜头数，
    服务于「选一版、删其余」的废弃视频清理流程。
    """
    counts: dict[str, int] = {"pending": 0, "pass": 0, "revise": 0, "redesign": 0}
    scores: list[int] = []
    groups: dict[tuple[str, str], list[ShotReviewItem]] = {}
    for item in session.items:
        counts[verdict_for_score(item.score)] += 1
        if item.score is not None:
            scores.append(item.score)
        groups.setdefault(_group_key(item), []).append(item)
    counts["total"] = len(session.items)
    counts["scored"] = len(scores)
    counts["prompts_revised"] = sum(1 for i in session.items if i.revised_prompt)
    counts["average_score"] = round(sum(scores) / len(scores), 1) if scores else None
    counts["multi_take_shots"] = sum(1 for v in groups.values() if len(v) > 1)
    counts["selected_shots"] = sum(1 for v in groups.values() if any(i.selected for i in v))
    return counts


def recompute_summary(db: Session, session: ShotReviewSession) -> dict:
    summary = compute_summary(session)
    session.summary_json = json.dumps(summary, ensure_ascii=False)
    session.updated_at = _now_iso()
    db.commit()
    return summary


# ---------------- 会话 CRUD ----------------

def create_session(db: Session, title: str, root_path: str) -> ShotReviewSession:
    """创建审片会话并立即扫描根目录。"""
    abs_root = is_shot_path_allowed(root_path)
    session = ShotReviewSession(
        id=_new_uuid(),
        title=title,
        root_path=str(abs_root),
        status="in_review",
        summary_json="{}",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    scan_root(db, session, str(abs_root))
    return session


def get_session(db: Session, session_id: str) -> ShotReviewSession | None:
    return db.get(ShotReviewSession, session_id)


def list_sessions(db: Session) -> list[ShotReviewSession]:
    from sqlalchemy import desc
    return db.query(ShotReviewSession).order_by(desc(ShotReviewSession.updated_at)).all()


def update_session(
    db: Session, session: ShotReviewSession, title: str | None, status: str | None
) -> ShotReviewSession:
    if title is not None:
        session.title = title
    if status is not None:
        session.status = status
    session.updated_at = _now_iso()
    db.commit()
    db.refresh(session)
    return session


def delete_session(db: Session, session: ShotReviewSession) -> None:
    thumb_dir = _thumb_base_path() / session.id
    if thumb_dir.exists():
        try:
            shutil.rmtree(str(thumb_dir))
        except OSError:
            pass
    db.delete(session)
    db.commit()


# ---------------- 条目读写 ----------------

def get_item(db: Session, item_id: str) -> ShotReviewItem | None:
    return db.get(ShotReviewItem, item_id)


def _set_selected(db: Session, item: ShotReviewItem, selected: bool) -> None:
    """设置「选定保留版本」标记；同一集 + 镜号分组下互斥，选中新版本自动取消旧选中。"""
    if not selected:
        item.selected = False
        return
    for other in item.session.items:
        if other.id != item.id and other.selected and _group_key(other) == _group_key(item):
            other.selected = False
    item.selected = True


def update_item(
    db: Session,
    item: ShotReviewItem,
    score: int | None,
    clear_score: bool,
    feedback: str | None,
    revised_prompt: str | None = None,
    selected: bool | None = None,
) -> ShotReviewItem:
    """更新单个条目：打分（clear_score=True 表示清除分数）、修改意见、精修提示词与选定标记。

    revised_prompt：None 表示不修改；空串/纯空白表示清除（落库为 NULL）。
    selected：None 表示不修改；True 表示选定为该镜保留版本（同组其余自动取消）。
    """
    if clear_score:
        item.score = None
    elif score is not None:
        item.score = score
    if feedback is not None:
        item.feedback = feedback
    if revised_prompt is not None:
        item.revised_prompt = revised_prompt.strip() or None
    if selected is not None:
        _set_selected(db, item, selected)
    item.reviewed_at = _now_iso()
    item.updated_at = _now_iso()
    db.commit()
    db.refresh(item)
    if item.session:
        recompute_summary(db, item.session)
    return item


def batch_update_items(db: Session, session_id: str, updates: list[dict]) -> tuple[int, int]:
    """批量更新审片条目。updates: [{id, score?, clear_score?, feedback?, revised_prompt?, selected?}]"""
    session = db.get(ShotReviewSession, session_id)
    items = {item.id: item for item in session.items} if session else {}
    updated = 0
    failed = 0
    for upd in updates:
        item = items.get(upd.get("id", ""))
        if not item:
            failed += 1
            continue
        if upd.get("clear_score"):
            item.score = None
        elif upd.get("score") is not None:
            item.score = upd["score"]
        if upd.get("feedback") is not None:
            item.feedback = upd["feedback"]
        if upd.get("revised_prompt") is not None:
            item.revised_prompt = str(upd["revised_prompt"]).strip() or None
        if upd.get("selected") is not None:
            _set_selected(db, item, bool(upd["selected"]))
        item.reviewed_at = _now_iso()
        item.updated_at = _now_iso()
        updated += 1
    db.commit()
    if session:
        recompute_summary(db, session)
    return updated, failed


# ---------------- 删除条目（废弃视频清理） ----------------

def _resolve_item_file_checked(item: ShotReviewItem) -> Path:
    """解析条目视频绝对路径并做双重路径校验：会话根目录必须在允许根目录之下，
    文件路径必须仍在会话根目录之内（防 file_path 被篡改后越界删除）。"""
    session = item.session
    if not session:
        raise ValueError("条目所属会话不存在")
    root = is_shot_path_allowed(session.root_path)
    path = (root / item.file_path).resolve()
    if not _is_within(path, root):
        raise ValueError(f"文件路径越界，拒绝删除: {item.file_path}")
    return path


def _delete_item_file(item: ShotReviewItem) -> int:
    """从磁盘删除条目对应的视频文件，返回释放的字节数。

    文件已不存在时视为成功（返回 0）；删除失败抛 ValueError/OSError 由上层转 HTTP 错误。
    """
    path = _resolve_item_file_checked(item)
    if not path.exists():
        return 0
    size = path.stat().st_size
    path.unlink()
    return size


def delete_item(db: Session, item: ShotReviewItem, delete_file: bool) -> dict:
    """删除审片条目；delete_file=True 时同时从磁盘删除该视频文件。"""
    freed_bytes = _delete_item_file(item) if delete_file else 0
    _delete_thumbnail_file(item.thumbnail_path)
    session = item.session
    db.delete(item)
    db.commit()
    if session:
        recompute_summary(db, session)
    return {"deleted": 1, "failed": 0, "freed_bytes": freed_bytes, "errors": []}


def bulk_delete_items(db: Session, session: ShotReviewSession, item_ids: list[str], delete_file: bool) -> dict:
    """批量删除审片条目（通常为同镜号下未选定的废弃版本），可选物理删除视频文件。

    单个文件删除失败不影响其余条目；错误逐条返回给前端展示。
    """
    items = {item.id: item for item in session.items}
    deleted = 0
    failed = 0
    freed_bytes = 0
    errors: list[dict] = []
    for item_id in item_ids:
        item = items.get(item_id)
        if not item:
            failed += 1
            errors.append({"id": item_id, "message": "条目不存在或已删除"})
            continue
        try:
            if delete_file:
                freed_bytes += _delete_item_file(item)
        except (ValueError, OSError) as e:
            failed += 1
            errors.append({"id": item_id, "file_name": item.file_name, "message": str(e)})
            continue
        _delete_thumbnail_file(item.thumbnail_path)
        db.delete(item)
        deleted += 1
    db.commit()
    if deleted:
        recompute_summary(db, session)
    return {"deleted": deleted, "failed": failed, "freed_bytes": freed_bytes, "errors": errors}


def resolve_item_file(item: ShotReviewItem) -> Path | None:
    """解析审片条目对应的视频绝对路径。"""
    session = item.session
    if not session:
        return None
    path = Path(session.root_path) / item.file_path
    return path if path.exists() else None


def resolve_thumbnail(item: ShotReviewItem) -> Path | None:
    return _resolve_thumbnail_path(item.thumbnail_path)


def ensure_thumbnail(db: Session, item: ShotReviewItem) -> Path | None:
    """按需生成缩略图并回写数据库，返回缩略图绝对路径。

    扫描阶段不抽帧（大批量视频会拖垮请求），因此在首次访问缩略图接口时才生成；
    生成成功后 thumbnail_path 落库，后续请求直接命中缓存文件。
    """
    cached = _resolve_thumbnail_path(item.thumbnail_path)
    if cached:
        return cached

    abs_file = resolve_item_file(item)
    if not abs_file:
        return None

    thumb_rel = _generate_review_thumbnail(abs_file, item.session_id, item.mime_type or "")
    if not thumb_rel:
        return None

    # 并发下同一镜头可能被重复请求：以先落库的路径为准，避免覆盖成另一份文件
    db.refresh(item)
    if not item.thumbnail_path:
        item.thumbnail_path = thumb_rel
        db.commit()
    else:
        _delete_thumbnail_file(thumb_rel)
    return _resolve_thumbnail_path(item.thumbnail_path)