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
- 扫描剧集视频根目录（如 分镜脚本/），只递归收集能唯一定位到 EPxx-Sxx 的镜头媒体
  （成片视频与以镜号命名的分镜图/关键帧）；连拍母版、无镜号的整段样片不入列表；
- 从相对路径与文件名解析集号/镜号/剧目，并关联同集 shots.md 与生成报告的分镜信息；
- 生成缩略图（复用制片人审阅的 ffmpeg 抽帧能力，落在 data/review_thumbs/ 下）；
- 打分（0–100）、修改意见、精修提示词的读写，以及按评分档位的汇总统计；
- 同镜号多版本管理：为同一栏目内的视频标记「选定保留版本」（组内互斥），
  并支持删除废弃版本条目及对应视频文件（路径经允许根目录双重校验）；
- 审阅中心内的返工生成：改写提示词后复用创作页任务管线重新生成，
  结果可直接采用为同镜号的新版本（文件落在 data/assets，不写外部素材目录）。

评分档位（对齐 ai-video-director 规范，由 score 派生，不落库）：
  ≥70 通过（pass）｜60–69 需重生成（revise）｜<60 需重新设计（redesign）｜未打分 待审（pending）。
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from sqlalchemy.orm import Session, object_session

from ..models import Asset, ShotReviewItem, ShotReviewRegeneration, ShotReviewSession, Task
from ..utils.file_utils import detect_mime_type
from ..utils.time_utils import now_iso as _now_iso
from . import shot_review_archive as _archive
from . import task_service
from .asset_service import resolve_asset_path as _resolve_asset_path
from .review_common import (
    delete_thumbnail_file as _delete_thumbnail_file,
    generate_review_thumbnail as _generate_review_thumbnail,
    is_shot_path_allowed,
    is_within as _is_within,
    probe_media_meta as _probe_media_meta,
    resolve_thumbnail_path as _resolve_thumbnail_path,
    thumb_base_path as _thumb_base_path,
)
from .shot_script_meta import (
    EPISODE_DIR_RE,
    find_episode_dir,
    load_episode_meta,
    locate_script_dir,
    parse_shot_key,
    shot_numbers_in,
)

# 镜头审片面向的成片视频
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".flv"}
# 以镜号命名的分镜图/关键帧同样纳入审阅（其余参考图不入列表，避免噪声）
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# 评分档位阈值
PASS_SCORE = 70
REVISE_SCORE = 60

# 返工生成任务的归属对话（受保护，便于在创作页历史里集中查看）
REGEN_CONVERSATION_TITLE = "审阅返工"

# 返工生成记录的非终态，用于列表接口按需同步任务状态
_REGEN_ACTIVE_STATUSES = {"pending", "queued", "running"}

_HEAD_BYTES = 1024
_ANCESTOR_PARTS = 6

# 中间产物目录：连拍母版、原始下载素材不属于任何单一镜头，整段视频不可逐镜打分。
# 即便其中文件按 EPxx-Sxx 命名也不收录——它们不是交付成片。
_NON_SHOT_DIR_NAMES = {"downloads"}


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


def content_type_of(item: ShotReviewItem) -> str:
    """条目的内容类型：image | video（任务卡片的类型标签与返工模式依据）。"""
    mime = (item.mime_type or "").lower()
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    return "image" if Path(item.file_name).suffix.lower() in _IMAGE_EXTS else "video"


# ---------------- 被引用资产（关联原生成任务） ----------------

# shots.md 的「【生成任务】… task <id>」行：扫描建卡时据此关联原生成任务。
# 外部制作流水线写入的提示词底稿带 task id，是「这一镜用了哪些参考素材」的唯一线索。
_TASK_ID_IN_PROMPT_RE = re.compile(r"\btask\s+([0-9a-fA-F-]{8,})", re.IGNORECASE)


def task_id_from_prompt(source_prompt: str | None) -> str | None:
    match = _TASK_ID_IN_PROMPT_RE.search(source_prompt or "")
    return match.group(1) if match else None


def stored_input_asset_ids(item: ShotReviewItem) -> list[str]:
    """读条目已落库的参考素材 id；兼容老数据缺列 / JSON 损坏。"""
    try:
        parsed = json.loads(getattr(item, "input_asset_ids_json", "[]") or "[]")
    except (TypeError, ValueError):
        return []
    return (
        [aid for aid in parsed if isinstance(aid, str) and aid]
        if isinstance(parsed, list)
        else []
    )


def _refs_of_task(task: Task) -> list[str]:
    """任务参数里的完整参考素材列表；旧任务只落首张时回落到 input_asset_id。"""
    try:
        params = json.loads(task.params_json or "{}")
    except (TypeError, ValueError):
        params = {}
    refs = params.get("input_asset_ids") if isinstance(params, dict) else None
    if isinstance(refs, list):
        return [aid for aid in refs if isinstance(aid, str) and aid]
    return [task.input_asset_id] if task.input_asset_id else []


def task_refs_for_prompt(
    db: Session,
    source_prompt: str | None,
    cache: dict[str, list[str]] | None = None,
) -> list[str]:
    """按提示词底稿里的 task id 取回原生成任务引用的参考素材。

    扫描建卡不经过 drama review-import，input_asset_ids_json 长期为空；返工面板
    因此拿不到首帧图 / 角色参考，会把带参考的生成悄悄退化成纯文本生成。
    """
    task_id = task_id_from_prompt(source_prompt)
    if not task_id:
        return []
    if cache is not None and task_id in cache:
        return cache[task_id]
    task = db.get(Task, task_id)
    refs = _refs_of_task(task) if task is not None else []
    if cache is not None:
        cache[task_id] = refs
    return refs


def task_refs_map(db: Session, items: list[ShotReviewItem]) -> dict[str, list[str]]:
    """列表接口批量派生：一次查出全部关联任务，避免逐条查库（整批可达数百镜）。"""
    by_item: dict[str, str] = {}
    for item in items:
        task_id = task_id_from_prompt(item.source_prompt)
        if task_id:
            by_item[item.id] = task_id
    if not by_item:
        return {}
    tasks = db.query(Task).filter(Task.id.in_(set(by_item.values()))).all()
    by_task = {task.id: _refs_of_task(task) for task in tasks}
    return {item_id: by_task.get(task_id, []) for item_id, task_id in by_item.items()}


# ---------------- 扫描 ----------------

def _read_head_bytes(abs_file: Path) -> bytes:
    try:
        with abs_file.open("rb") as fh:
            return fh.read(_HEAD_BYTES)
    except OSError:
        return b""


def _identity_from_path(
    parts: list[str],
    abs_file: Path | None = None,
    abs_root: Path | None = None,
) -> tuple[str | None, str | None]:
    """只凭路径判断能否唯一定位一个镜头 (EPxx, Sxx)。

    扫描过滤与建档解析共用这套判定，避免「收进来时以为有镜号、建档时却是 S??」。
    镜头在审片列表里的身份必须是 EPxx-Sxx：只有镜号没有集号的分段样片
    （如 06_开头样片/clips/S01.mp4）会跨集撞号，不算已标识镜头。
    """
    file_episode, file_shot = parse_shot_key(parts[-1])
    episode = find_episode_dir(parts[:-1]) or file_episode
    shot_no = file_shot or parse_shot_key(*parts[:-1])[1]
    # 项目根本身可能是 EPxx 剧集目录（含 shots.md）：此时集号来自分镜目录而非路径
    if episode is None and abs_file is not None and abs_root is not None:
        script_dir = locate_script_dir(abs_file, abs_root)
        if script_dir is not None and EPISODE_DIR_RE.match(script_dir.name):
            episode = script_dir.name.upper()
    return episode, shot_no


def _collect_videos(abs_root: Path) -> dict[str, Path]:
    """递归收集可审阅的镜头媒体，键为相对根目录的 posix 路径。

    镜头审片是逐镜打分，只收录能唯一定位到 EPxx-Sxx 的媒体：连拍母版、
    开头样片分段、无镜号参考片这类整段视频进列表只会形成 S?? 空壳卡片。

    跳过目录：
    - ``_`` 开头：``_takes`` / ``_superseded_*`` / ``_model_compare`` 等辅助产物
      或历史版本，混入会与当前交付版本在同一镜号下重复出现，干扰打分；
    - ``downloads`` 等中间产物目录（``_NON_SHOT_DIR_NAMES``）：原始下载素材与
      连拍母版不属于任何单一镜头，即使文件按镜号命名也不是可逐镜审阅的成片。

    此外，文件名同时写着多个镜号的跨镜共用素材（背景板、对照图）也不收录。
    """
    found: dict[str, Path] = {}
    for child in abs_root.rglob("*"):
        if not child.is_file():
            continue
        suffix = child.suffix.lower()
        if suffix not in _VIDEO_EXTS and suffix not in _IMAGE_EXTS:
            continue
        rel = child.relative_to(abs_root)
        parts = [str(part) for part in rel.parts]
        if any(
            part.startswith("_") or part.lower() in _NON_SHOT_DIR_NAMES
            for part in parts[:-1]
        ):
            continue
        # 跨镜共用素材（文件名同时写了多个镜号，如 ep01_s08_s12_backdrop.png）
        # 不是某一镜的成片，收进来会与正式镜头拼成假的「同镜多版本」
        if len(shot_numbers_in(parts[-1])) > 1:
            continue
        episode, shot_no = _identity_from_path(parts, child, abs_root)
        if not (episode and shot_no):
            continue
        found[str(rel).replace("\\", "/")] = child
    return found


def _resolve_drama_title(abs_root: Path, rel: str, script_dir: Path | None) -> str:
    """解析剧目名称：优先取集号目录（含 shots.md 的 EPxx）的上级目录名。

    找不到分镜目录时退回「集号目录在相对路径中的前一级」，再退回扫描根目录名，
    保证卡片上的剧目标签永远有值。
    """
    if script_dir is not None and script_dir.parent.name:
        return script_dir.parent.name
    parts = rel.split("/")[:-1]
    for idx, part in enumerate(parts):
        if EPISODE_DIR_RE.match(part) and idx > 0:
            return parts[idx - 1]
    return abs_root.name


def _resolve_identity(rel: str, abs_root: Path, meta_cache: dict[Path, dict]) -> tuple[str | None, str | None, str, dict]:
    """解析 (episode, shot_no, shot_id, 分镜元信息)。

    身份判定与扫描过滤共用 ``_identity_from_path``（集号取路径中的 EPxx 目录、
    文件名前缀或含 shots.md 的剧集目录；镜号取文件名/路径中的 Sxx）。扫描阶段
    已排除无法唯一定位镜头的媒体；这里的 ``S??`` 回落只服务于返工生成等显式
    建档路径，不会再出现在扫描结果里。
    """
    parts = rel.split("/")
    abs_file = abs_root / rel
    episode, shot_no = _identity_from_path(parts, abs_file, abs_root)

    script_dir = locate_script_dir(abs_file, abs_root)
    shot_id = f"{episode}-{shot_no}" if episode and shot_no else (shot_no or "S??")

    meta: dict = {}
    if script_dir is not None and shot_no:
        if script_dir not in meta_cache:
            meta_cache[script_dir] = load_episode_meta(script_dir)
        meta = meta_cache[script_dir].get(shot_no, {})
    return episode, shot_no, shot_id, meta


def _build_item(
    session_id: str,
    abs_root: Path,
    rel: str,
    meta_cache: dict[Path, dict],
    db: Session,
    task_ref_cache: dict[str, list[str]],
) -> ShotReviewItem:
    abs_file = abs_root / rel
    episode, _, shot_id, meta = _resolve_identity(rel, abs_root, meta_cache)
    script_dir = locate_script_dir(abs_file, abs_root)
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
        drama_title=_resolve_drama_title(abs_root, rel, script_dir),
        file_path=rel,
        file_name=abs_file.name,
        origin="scan",
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
        # 扫描建卡也带上原生成任务的参考素材，卡片与返工面板才有「被引用资产」
        input_asset_ids_json=json.dumps(
            task_refs_for_prompt(db, meta.get("prompt_source"), task_ref_cache),
            ensure_ascii=False,
        ),
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
    # 连拍母版下多个镜头共用一个生成任务，缓存避免逐镜重复查库
    task_ref_cache: dict[str, list[str]] = {}
    added = 0
    added_keys: list[tuple[str | None, str]] = []
    for rel in sorted(found, key=str.lower):
        if rel in existing:
            continue
        item = _build_item(session.id, abs_root, rel, meta_cache, db, task_ref_cache)
        db.add(item)
        session.items.append(item)
        added += 1
        added_keys.append((item.episode, item.shot_id))

    removed = 0
    removed_keys: list[tuple[str | None, str]] = []
    scan_overrides: list[dict] = []
    backfilled = 0
    for rel, item in existing.items():
        # 返工生成产生的版本不在目录里，属于会话自有数据，不参与「文件已消失」比对
        if item.asset_id:
            continue
        if rel not in found:
            removed_keys.append((item.episode, item.shot_id))
            scan_overrides.append(_archive.missing_override(item))
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
        # 旧条目回填剧目名称（任务卡片分类标签）
        if not item.drama_title:
            script_dir = locate_script_dir(abs_root / rel, abs_root)
            item.drama_title = _resolve_drama_title(abs_root, rel, script_dir)
            backfilled += 1
        # 历史扫描卡片没有参考素材：按底稿里的 task id 从原生成任务补回，
        # 不覆盖 review-import / 返工采用已经落库的资产清单
        if not stored_input_asset_ids(item):
            refs = task_refs_for_prompt(db, item.source_prompt, task_ref_cache)
            if refs:
                item.input_asset_ids_json = json.dumps(refs, ensure_ascii=False)
                backfilled += 1
    if backfilled:
        db.flush()

    _reindex(db, session)
    session.updated_at = _now_iso()
    db.commit()
    recompute_summary(db, session)
    # 数据沉淀：为涉及镜号建档/更新（新镜建档、外部消失标记），审阅人无感
    _archive.after_scan(db, session, touched=added_keys + removed_keys, overrides=scan_overrides)
    return {"added": added, "removed": removed, "total": len(session.items)}


def _reindex(db: Session, session: ShotReviewSession) -> None:
    db.flush()
    for order, item in enumerate(sorted(session.items, key=_sort_key)):
        item.sort_order = order


# ---------------- 导入（外部制作流程的成片镜头） ----------------

# 导入时可刷新的分镜 / 生成元信息字段；评分、意见、精修提示词与选定标记不在其中，
# 重复导入只更新「应有 vs 实际」的事实，绝不覆盖审阅结论。
_IMPORTABLE_META = (
    "drama_title",
    "source_prompt",
    "shot_function",
    "script_duration",
    "shot_size",
    "movement",
    "dialogue",
    "render_status",
    "model",
)


def import_items(db: Session, session: ShotReviewSession, rows: list[dict]) -> dict:
    """按调用方给出的清单导入审片条目（不扫描目录，逐条建档）。

    与 scan_root 的分工：扫描只能收录「文件名里带镜号」的媒体，分镜与生成任务的
    信息要靠在素材目录里找 shots.md 与生成报告；导入则把另一条制作流水线已经知道的
    事实（分镜定义、提示词、模型、生成状态、实测时长）直接带进来，因此能把外部项目
    的成片镜头连同上下文一起搬进审片中心。

    安全与幂等：
    - 相对路径必须落在会话根目录内且文件真实存在，越界或缺失计入 missing 并原样返回，
      由调用方决定是否处理，不静默丢弃；
    - 与扫描同一道门禁：只收能唯一定位到 EPxx-Sxx 的镜头，无集号/无镜号的整段视频
      （连拍母版、样片）计入 skipped，不建档；
    - 以 (集号, 镜号, 文件路径) 去重：已存在则只刷新元信息，评分/意见/精修提示词/
      选定标记一律保留。
    """
    root = is_shot_path_allowed(session.root_path)
    existing = {(i.episode or "", i.shot_id, i.file_path): i for i in session.items}
    added = 0
    updated = 0
    skipped = 0
    missing: list[dict] = []
    touched: list[tuple[str | None, str]] = []

    for row in rows:
        rel = str(row.get("file_path") or "").replace("\\", "/").strip().lstrip("/")
        shot_id = str(row.get("shot_id") or "").strip()
        episode = row.get("episode") or None
        if not rel or not shot_id:
            skipped += 1
            continue
        # 审片列表只收已标识镜头：与扫描过滤同一套判定，杜绝从导入接口
        # 把连拍母版、无镜号样片这类整段视频带成 S?? 空壳卡片。
        if not episode or not parse_shot_key(shot_id)[1]:
            skipped += 1
            continue

        abs_file = (root / rel).resolve()
        if not _is_within(abs_file, root) or not abs_file.is_file():
            missing.append({
                "episode": episode,
                "shot_id": shot_id,
                "file_path": rel,
                "message": "文件不存在或路径越界",
            })
            continue

        duration = row.get("duration")
        item = existing.get((episode or "", shot_id, rel))
        if item is None:
            mime_type = detect_mime_type(abs_file.name, _read_head_bytes(abs_file))
            width, height, probed_duration = _probe_media_meta(abs_file, mime_type)
            item = ShotReviewItem(
                id=_new_uuid(),
                session_id=session.id,
                episode=episode,
                shot_id=shot_id,
                file_path=rel,
                file_name=abs_file.name,
                origin="scan",
                file_size=abs_file.stat().st_size,
                mime_type=mime_type,
                width=width,
                height=height,
                # 分镜/生产状态里的实测时长优先：与脚本时长同源，便于「应有 vs 实际」对照
                duration=duration if duration is not None else probed_duration,
                thumbnail_path=None,
                score=None,
                feedback="",
                selected=False,
                sort_order=0,
            )
            db.add(item)
            session.items.append(item)
            existing[(episode or "", shot_id, rel)] = item
            added += 1
        else:
            updated += 1

        for field in _IMPORTABLE_META:
            value = row.get(field)
            if value is not None:
                setattr(item, field, value)
        # 参考素材 id 列表单独落库（不走 _IMPORTABLE_META 的字符串直写白名单）：
        # 只有本次导入明确带了该字段才刷新，避免重复导入未带该字段的旧清单时
        # 把已有值覆盖成空，造成数据倒退。
        if "input_asset_ids" in row and row["input_asset_ids"] is not None:
            raw = row["input_asset_ids"]
            ids = (
                [aid for aid in raw if isinstance(aid, str) and aid]
                if isinstance(raw, list) else []
            )
            item.input_asset_ids_json = json.dumps(ids, ensure_ascii=False)
        if duration is not None:
            item.duration = duration
        item.updated_at = _now_iso()
        touched.append((episode, shot_id))

    db.flush()
    _reindex(db, session)
    session.updated_at = _now_iso()
    db.commit()
    recompute_summary(db, session)
    if touched:
        # 数据沉淀：导入即建档，审阅人首次打开时 entry.md 已带着分镜与提示词
        _archive.after_scan(db, session, touched=touched)

    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "total": len(session.items),
        "missing": missing[:50],
        "missing_count": len(missing),
    }


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

def create_session(
    db: Session, title: str, root_path: str, scan: bool = True
) -> ShotReviewSession:
    """创建审片会话；scan=True 时立即扫描根目录。

    scan=False 用于「导入」流程：调用方自带条目清单（含分镜与生成任务元数据），
    若先扫描一遍目录，会把同目录下的参考素材、开场样片等一并收进审片列表，
    与导入的镜头重复且噪声大。只创建空会话，随后由 import_items 逐条建档。
    """
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
    if scan:
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
    # 数据沉淀：标记完成时归档每镜首末版本媒体并全量刷新；其余变更同步全局索引
    if status == "completed":
        _archive.finalize_session(db, session)
    else:
        _archive.refresh_index(db)
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
    # 数据沉淀：档案文件夹保留，全局索引标记「会话已删除」
    _archive.refresh_index(db)


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
    # 数据沉淀：评分/意见/精修提示词/选定 → 重写该镜 entry.md，审阅人无感
    _archive.sync_shots(item.session, [item])
    return item


def batch_update_items(db: Session, session_id: str, updates: list[dict]) -> tuple[int, int]:
    """批量更新审片条目。updates: [{id, score?, clear_score?, feedback?, revised_prompt?, selected?}]"""
    session = db.get(ShotReviewSession, session_id)
    items = {item.id: item for item in session.items} if session else {}
    updated = 0
    failed = 0
    updated_items: list[ShotReviewItem] = []
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
        updated_items.append(item)
    db.commit()
    if session:
        recompute_summary(db, session)
        # 数据沉淀：批量更新涉及的镜号建档刷新
        _archive.sync_shots(session, updated_items)
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
    返工生成的版本（asset_id 非空）不删资产文件：素材库中的产出可能被其他任务复用，
    这里只把条目移出审片列表，避免误删。
    """
    if item.asset_id:
        return 0
    path = _resolve_item_file_checked(item)
    if not path.exists():
        return 0
    size = path.stat().st_size
    path.unlink()
    return size


def delete_item(db: Session, item: ShotReviewItem, delete_file: bool) -> dict:
    """删除审片条目；delete_file=True 时同时从磁盘删除该视频文件。"""
    # 数据沉淀：删前抢救媒体副本（物理删除后无法复制），随后标记版本状态
    rescue = _archive.rescue_before_delete(item, delete_file)
    freed_bytes = _delete_item_file(item) if delete_file else 0
    _delete_thumbnail_file(item.thumbnail_path)
    session = item.session
    db.delete(item)
    db.commit()
    if session:
        recompute_summary(db, session)
    if rescue:
        _archive.apply_delete_overrides(db, session, [rescue])
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
    rescues: list[dict] = []
    for item_id in item_ids:
        item = items.get(item_id)
        if not item:
            failed += 1
            errors.append({"id": item_id, "message": "条目不存在或已删除"})
            continue
        # 数据沉淀：删前抢救副本（必须在文件删除前复制）；删除失败则不追加覆盖标记，
        # 条目仍在库中，该镜号下次更新时会按库内状态重写档案
        rescue = _archive.rescue_before_delete(item, delete_file)
        try:
            if delete_file:
                freed_bytes += _delete_item_file(item)
        except (ValueError, OSError) as e:
            failed += 1
            errors.append({"id": item_id, "file_name": item.file_name, "message": str(e)})
            continue
        if rescue:
            rescues.append(rescue)
        _delete_thumbnail_file(item.thumbnail_path)
        db.delete(item)
        deleted += 1
    db.commit()
    if deleted:
        recompute_summary(db, session)
    if rescues:
        _archive.apply_delete_overrides(db, session, rescues)
    return {"deleted": deleted, "failed": failed, "freed_bytes": freed_bytes, "errors": errors}


def _asset_of(item: ShotReviewItem) -> Asset | None:
    """取条目关联的资产（返工生成产物），非资产条目返回 None。"""
    if not item.asset_id:
        return None
    db = object_session(item)
    return db.get(Asset, item.asset_id) if db is not None else None


def resolve_item_file(item: ShotReviewItem) -> Path | None:
    """解析审片条目对应的媒体绝对路径。

    扫描条目取会话根目录下的相对路径；返工生成条目取资产文件（data/assets）。
    """
    if item.asset_id:
        asset = _asset_of(item)
        return _resolve_asset_path(asset) if asset else None
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


# ---------------- 返工生成（任务卡片内改提示词重生成） ----------------

def _derive_regen_task_type(content_type: str, has_ref: bool) -> str:
    """内容类型 + 是否带参考素材 → 任务类型（与创作页 deriveTaskType 同规则）。"""
    if content_type == "image":
        return "img2img" if has_ref else "text2img"
    return "img2video" if has_ref else "text2video"


def _regen_asset_ids(task: Task) -> list[str]:
    """任务结果资产 id（优先 worker 落库的有序列表）。"""
    params = task_service.safe_json_loads(task.params_json, {})
    stored = params.get("result_asset_ids")
    if isinstance(stored, list) and stored:
        return [str(a) for a in stored]
    return []


def create_regeneration(
    db: Session,
    item: ShotReviewItem,
    *,
    prompt: str,
    provider: str,
    model_id: str | None,
    params: dict,
    input_asset_ids: list[str],
    task_type: str | None = None,
) -> ShotReviewRegeneration:
    """按任务卡片上改写的提示词创建一次返工生成任务（尚未入队）。

    生成本身完全复用创作页的任务管线：同样的 Provider/模型/参数、同样的
    params_json 契约（含 result_asset_ids），因此进度、结果资产、失败原因
    都能直接沿用现有 SSE 与任务中心；本表只额外记录「哪一镜、用什么提示词返工」。

    入队由调用方负责（与 /tasks 创建接口一致，便于入队失败时明确报错）。
    """
    session = item.session
    if not session:
        raise ValueError("条目所属会话不存在")
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        raise ValueError("提示词不能为空")

    refs = [aid for aid in (input_asset_ids or []) if aid]
    content_type = content_type_of(item)
    resolved_type = task_type or _derive_regen_task_type(content_type, bool(refs))
    if resolved_type in {"img2img", "img2video"} and not refs:
        raise ValueError("图生图/图生视频需要至少一个参考素材")

    task_params = dict(params or {})
    if refs:
        task_params["input_asset_ids"] = refs
    # 返工来源标记：任务中心可据此回溯本次生成来自哪个审片条目的哪一镜
    task_params.update(
        {
            "review_session_id": session.id,
            "review_item_id": item.id,
            "review_episode": item.episode,
            "review_shot_id": item.shot_id,
            "content_mode": content_type,
        }
    )

    conversation = task_service.get_or_create_conversation(db, REGEN_CONVERSATION_TITLE)
    task = Task(
        id=_new_uuid(),
        type=resolved_type,
        status="pending",
        progress=0,
        provider=provider,
        model_id=model_id,
        prompt=cleaned_prompt,
        params_json=json.dumps(task_params, ensure_ascii=False),
        input_asset_id=refs[0] if refs else None,
        conversation_id=conversation.id,
    )
    db.add(task)

    regen = ShotReviewRegeneration(
        id=_new_uuid(),
        session_id=session.id,
        item_id=item.id,
        episode=item.episode,
        shot_id=item.shot_id,
        task_id=task.id,
        prompt=cleaned_prompt,
        provider=provider,
        model_id=model_id,
        task_type=resolved_type,
        params_json=json.dumps(params or {}, ensure_ascii=False),
        status="pending",
        progress=0,
    )
    db.add(regen)
    db.commit()
    db.refresh(regen)
    return regen


def sync_regeneration(db: Session, regen: ShotReviewRegeneration) -> ShotReviewRegeneration:
    """把任务的最新状态同步回返工记录（终态不再查询，避免重复写库）。"""
    if regen.status not in _REGEN_ACTIVE_STATUSES or not regen.task_id:
        return regen
    task = db.get(Task, regen.task_id)
    if task is None:
        return regen

    changed = False
    status = task.status
    if regen.status != status:
        regen.status = status
        changed = True
    if regen.progress != task.progress:
        regen.progress = task.progress
        changed = True
    if task.error_msg and regen.error_msg != task.error_msg:
        regen.error_msg = task.error_msg
        changed = True
    if status == "completed":
        asset_ids = _regen_asset_ids(task)
        if asset_ids and regen.result_asset_id != asset_ids[0]:
            regen.result_asset_id = asset_ids[0]
            changed = True
    if changed:
        regen.updated_at = _now_iso()
        db.commit()
        db.refresh(regen)
    return regen


def list_regenerations(db: Session, session_id: str) -> list[ShotReviewRegeneration]:
    """会话内的全部返工记录（含已放弃的，前端按状态过滤），顺手同步在途任务。"""
    from sqlalchemy import desc

    regens = (
        db.query(ShotReviewRegeneration)
        .filter(ShotReviewRegeneration.session_id == session_id)
        .order_by(desc(ShotReviewRegeneration.created_at))
        .all()
    )
    for regen in regens:
        sync_regeneration(db, regen)
    return regens


def get_regeneration(db: Session, regen_id: str) -> ShotReviewRegeneration | None:
    return db.get(ShotReviewRegeneration, regen_id)


def _regen_version_name(db: Session, regen: ShotReviewRegeneration, suffix: str) -> str:
    """返工版本的文件名：{镜号}__regen{N}{后缀}，N 在该镜已采用版本中递增。"""
    used = (
        db.query(ShotReviewItem)
        .filter(
            ShotReviewItem.session_id == regen.session_id,
            ShotReviewItem.shot_id == regen.shot_id,
            ShotReviewItem.origin == "regen",
        )
        .count()
    )
    return f"{regen.shot_id}__regen{used + 1}{suffix}"


def adopt_regeneration(db: Session, regen: ShotReviewRegeneration) -> ShotReviewItem:
    """把返工结果采用为同镜号的一个新版本（自动选定为保留版本）。

    生成产物落在 data/assets，不写回外部素材目录：新条目用 asset_id 指向资产，
    实体文件仍归素材库管理；审阅结论、评分与版本链与其他版本完全一致。
    """
    regen = sync_regeneration(db, regen)
    if regen.status != "completed" or not regen.result_asset_id:
        raise ValueError("该返工结果尚未生成成功，无法采用")

    if regen.adopted_item_id:
        existing = db.get(ShotReviewItem, regen.adopted_item_id)
        if existing:
            return existing

    source = db.get(ShotReviewItem, regen.item_id)
    if source is None:
        raise ValueError("原审片条目已删除，无法采用该结果")
    session = source.session
    if session is None:
        raise ValueError("条目所属会话不存在")

    asset = db.get(Asset, regen.result_asset_id)
    if asset is None:
        raise ValueError("生成结果资产不存在，无法采用")

    suffix = Path(asset.file_path).suffix or (
        ".png" if content_type_of(source) == "image" else ".mp4"
    )
    file_name = _regen_version_name(db, regen, suffix)

    # 本次返工任务引用的参考素材：继承进新版本，供提示词编辑器展示同源缩略图
    regen_refs: list[str] = []
    if regen.task_id:
        regen_task = db.get(Task, regen.task_id)
        if regen_task is not None:
            try:
                task_params = json.loads(regen_task.params_json or "{}")
            except (TypeError, ValueError):
                task_params = {}
            raw_refs = task_params.get("input_asset_ids") if isinstance(task_params, dict) else None
            if isinstance(raw_refs, list):
                regen_refs = [aid for aid in raw_refs if isinstance(aid, str) and aid]

    item = ShotReviewItem(
        id=_new_uuid(),
        session_id=session.id,
        episode=source.episode,
        shot_id=source.shot_id,
        drama_title=source.drama_title,
        file_path=file_name,
        file_name=file_name,
        asset_id=asset.id,
        origin="regen",
        file_size=asset.file_size,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        duration=asset.duration,
        thumbnail_path=None,
        score=None,
        feedback="",
        selected=False,
        source_prompt=regen.prompt,
        revised_prompt=regen.prompt,
        shot_function=source.shot_function,
        script_duration=source.script_duration,
        shot_size=source.shot_size,
        movement=source.movement,
        dialogue=source.dialogue,
        render_status="completed",
        model=regen.model_id,
        input_asset_ids_json=json.dumps(regen_refs, ensure_ascii=False),
        sort_order=source.sort_order,
    )
    db.add(item)
    session.items.append(item)
    db.flush()
    # 新版本默认选定为保留版本：返工就是为了替换掉不满意的旧版本
    _set_selected(db, item, True)
    _reindex(db, session)
    regen.adopted_item_id = item.id
    regen.updated_at = _now_iso()
    session.updated_at = _now_iso()
    db.commit()
    db.refresh(item)
    recompute_summary(db, session)
    # 数据沉淀：新版本的提示词与来源一并写入该镜档案
    _archive.sync_shots(session, [item])
    return item


def discard_regeneration(db: Session, regen: ShotReviewRegeneration) -> ShotReviewRegeneration:
    """放弃某次返工结果（软删除留痕，不删除任务与资产）。"""
    if regen.adopted_item_id:
        raise ValueError("该结果已采用为新版本，无法放弃")
    regen.status = "discarded"
    regen.updated_at = _now_iso()
    db.commit()
    db.refresh(regen)
    return regen