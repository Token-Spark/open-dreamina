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

"""镜头审片数据沉淀（markdown 归档）。

审阅过程中产生的「原内容 → 评分 → 存在的问题 → 修改指引 → 修改后内容」
迭代数据以纯 markdown + 媒体副本文件夹的形式沉淀在归档目录中，供后续优化
AI 工作流与提示词使用。设计约束：

- **审阅人无感**：所有写入挂在 shot_review_service 审阅动作的收尾处；
  本模块每个公开函数自行捕获全部异常并只记日志，绝不影响审片主流程。
- **不使用数据库**：仅产出 markdown 与媒体副本；entry.md 末尾带一段 HTML
  注释形式的机器缓存（open-dreamina-archive-cache），保存历史版本（含已
  移出会话 / 已物理删除的版本）的元数据，用于版本离开数据库后仍能完整
  重绘版本链。该注释对人与 AI 阅读不可见。

目录结构::

    {archive_dir}/
      INDEX.md                                  # 全局索引：所有会话一览
      {date}-{title_slug}-{session_id[:8]}/     # 每会话一个文件夹
        session.md                              # 会话概览 + 镜号索引表
        EP01/EP01-S01/entry.md                  # 该镜完整档案（版本链 + 审阅数据）
        EP01/EP01-S01/media/{id8}--{file_name}  # 媒体归档副本

无感写入时机（对应 shot_review_service 中的调用点）::

    update_item / batch_update_items   -> sync_shots            重写涉及镜号的 entry.md
    delete_item / bulk_delete_items    -> rescue_before_delete  删文件前抢救媒体副本
                                       -> apply_delete_overrides 版本标记已废弃/已移出并刷新
    scan_root（创建/重新扫描）          -> after_scan            新镜建档、外部消失标记、刷新索引
    update_session(status=completed)   -> finalize_session      归档每镜首末版本媒体 + 全量刷新
    delete_session                     -> refresh_index         档案文件夹保留，索引标记会话已删除
"""
from __future__ import annotations

import json
import logging
import math
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import settings
from ..utils.time_utils import now_iso

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from ..models import ShotReviewItem, ShotReviewSession

logger = logging.getLogger(__name__)

# 评分档位阈值与文案（与 shot_review_service 保持一致；verdict 经惰性导入复用）
VERDICT_LABELS = {
    "pass": "通过",
    "revise": "需重生成",
    "redesign": "需重新设计",
    "pending": "待审（未评分）",
}
SESSION_STATUS_LABELS = {
    "draft": "草稿",
    "in_review": "审片中",
    "completed": "已完成",
    "archived": "已归档",
}

# entry.md 末尾的机器缓存标记（HTML 注释，渲染不可见）
_CACHE_BEGIN = "<!-- open-dreamina-archive-cache"
_CACHE_END = "-->"

_UNPARSED_EPISODE = "_unparsed"

_SANITIZE_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_SHOT_NO_RE = re.compile(r"S(\d+)", re.IGNORECASE)


# ---------------- 基础工具 ----------------

def _enabled() -> bool:
    return bool(settings.shot_review_archive_enabled)


def _archive_root() -> Path:
    return settings.shot_review_archive_path


def _copy_media_enabled() -> bool:
    return bool(settings.shot_review_archive_copy_media)


def _verdict_of(score: int | None) -> str:
    from .shot_review_service import verdict_for_score

    return verdict_for_score(score)


def _verdict_label(score: int | None) -> str:
    return VERDICT_LABELS.get(_verdict_of(score), VERDICT_LABELS["pending"])


def _slugify(text: str, max_len: int = 40) -> str:
    cleaned = _SANITIZE_RE.sub("", (text or "").strip()).strip(". ")
    cleaned = re.sub(r"\s+", "-", cleaned)
    return cleaned[:max_len].strip("-. ") or "未命名"


def _safe_component(text: str | None) -> str:
    cleaned = _SANITIZE_RE.sub("_", (text or "").strip()).strip(". ")
    return cleaned or "_"


def _shot_no_of(shot_id: str | None) -> int:
    m = _SHOT_NO_RE.search(shot_id or "")
    return int(m.group(1)) if m else math.inf


def _fmt_ts(ts: float | None) -> str:
    if ts is None:
        return "未知时间"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "未知时间"


def _fmt_iso(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def _human_size(n: int | float | None) -> str:
    size = float(n or 0)
    if size <= 0:
        return "未知大小"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def _yaml_line(key: str, value) -> str:
    """渲染一行 frontmatter。字符串用 json.dumps 产出（双引号标量同时是合法 YAML）。"""
    if value is None:
        return f"{key}:"
    if isinstance(value, bool):
        return f"{key}: {'true' if value else 'false'}"
    if isinstance(value, (int, float)):
        return f"{key}: {value}"
    return f"{key}: {json.dumps(str(value), ensure_ascii=False)}"


def _fence_text(text: str | None) -> str:
    t = (text or "").strip()
    if not t:
        return "（无）"
    fence = "```"
    while fence in t:
        fence += "`"
    return f"{fence}text\n{t}\n{fence}"


def _quote(text: str | None) -> str:
    t = (text or "").strip()
    if not t:
        return "（未填写）"
    return "\n".join(f"> {line}" for line in t.splitlines() or [""])


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{uuid.uuid4().hex[:8]}")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _group_key(item: "ShotReviewItem") -> tuple[str, str]:
    return (item.episode or "", item.shot_id or "S??")


def _shot_dir(session_dir: Path, episode: str | None, shot_id: str | None) -> Path:
    return session_dir / _safe_component(episode or _UNPARSED_EPISODE) / _safe_component(shot_id or "S??")


def _session_dir(session: "ShotReviewSession", create: bool = False) -> Path:
    """会话归档文件夹：日期-标题slug-id前8位。按 id 后缀匹配既有文件夹，
    会话改名不改变文件夹名（链接稳定）。"""
    root = _archive_root()
    id8 = session.id[:8]
    if root.exists():
        for child in sorted(root.iterdir()):
            if child.is_dir() and child.name.endswith(f"-{id8}"):
                return child
    date_part = (session.created_at or now_iso())[:10].replace("-", "")
    path = root / f"{date_part}-{_slugify(session.title)}-{id8}"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _item_abs_file(item: "ShotReviewItem") -> Path | None:
    session = item.session
    if not session:
        return None
    path = Path(session.root_path) / item.file_path
    return path if path.exists() else None


def _item_mtime(item: "ShotReviewItem") -> float | None:
    abs_file = _item_abs_file(item)
    if abs_file is None:
        return None
    try:
        return abs_file.stat().st_mtime
    except OSError:
        return None


# ---------------- 缓存读写 ----------------

def _load_cache(entry_path: Path) -> tuple[dict, dict[str, dict]]:
    """读取 entry.md 末尾的机器缓存，返回 (镜级元信息, item_id → 版本元数据)。"""
    try:
        text = entry_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}, {}
    if _CACHE_BEGIN not in text:
        return {}, {}
    blob = text.split(_CACHE_BEGIN, 1)[1].split(_CACHE_END, 1)[0].strip()
    try:
        data = json.loads(blob)
        shot = data.get("shot") if isinstance(data, dict) else None
        versions = data.get("versions") if isinstance(data, dict) else None
        if not isinstance(shot, dict) or not isinstance(versions, list):
            return {}, {}
        by_id = {v["item_id"]: v for v in versions if isinstance(v, dict) and v.get("item_id")}
        return shot, by_id
    except (json.JSONDecodeError, TypeError, KeyError):
        logger.warning("审片归档缓存解析失败，将重建: %s", entry_path)
        return {}, {}


def _dump_cache(shot_meta: dict, versions: list[dict]) -> str:
    payload = {"saved_at": now_iso(), "shot": shot_meta, "versions": versions}
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"{_CACHE_BEGIN}\n{blob}\n{_CACHE_END}"


def _version_sort_key(v: dict) -> tuple:
    mtime = v.get("mtime")
    return (mtime if isinstance(mtime, (int, float)) else math.inf, v.get("file_name") or "")


def _version_from_item(item: "ShotReviewItem") -> dict:
    return {
        "item_id": item.id,
        "file_name": item.file_name,
        "file_path": item.file_path,
        "mtime": _item_mtime(item),
        "size": item.file_size,
        "width": item.width,
        "height": item.height,
        "duration": item.duration,
        "model": item.model,
        "render_status": item.render_status,
        "source_prompt": item.source_prompt,
        "score": item.score,
        "verdict": _verdict_of(item.score),
        "feedback": item.feedback or "",
        "revised_prompt": item.revised_prompt,
        "selected": bool(item.selected),
        "reviewed_at": item.reviewed_at,
        "updated_at": item.updated_at,
    }


def _merge_shot_meta(shot_meta: dict, items: list["ShotReviewItem"]) -> None:
    for it in items:
        if it.source_prompt and not shot_meta.get("source_prompt"):
            shot_meta["source_prompt"] = it.source_prompt
        for key in ("shot_function", "shot_size", "movement", "dialogue", "script_duration"):
            val = getattr(it, key, None)
            if val and not shot_meta.get(key):
                shot_meta[key] = val


# ---------------- 媒体归档 ----------------

def _archive_media_copy(item_id: str, file_name: str, abs_file: Path, media_dir: Path) -> str | None:
    """复制媒体副本到归档，返回 entry.md 中的相对引用；未复制返回 None。"""
    if not _copy_media_enabled() or not abs_file.exists():
        return None
    target = media_dir / f"{item_id[:8]}--{_safe_component(file_name)}"
    try:
        if not target.exists() or target.stat().st_size != abs_file.stat().st_size:
            media_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(abs_file), str(target))
        return f"media/{target.name}"
    except OSError as e:
        logger.warning("审片归档复制媒体失败 %s: %s", abs_file, e)
        return None


def _ensure_archived(session: "ShotReviewSession", session_dir: Path, item: "ShotReviewItem",
                     cached: dict | None) -> str | None:
    """确保该版本有媒体副本（已有则跳过），返回 archived_as 相对引用。"""
    if cached and cached.get("archived_as"):
        return cached["archived_as"]
    abs_file = _item_abs_file(item)
    if abs_file is None:
        return None
    media_dir = _shot_dir(session_dir, item.episode, item.shot_id) / "media"
    return _archive_media_copy(item.id, item.file_name, abs_file, media_dir)


# ---------------- entry.md 渲染 ----------------

def _status_label(v: dict, total_versions: int) -> str:
    status = v.get("status") or "active"
    if status == "deleted":
        return "已废弃（文件已删除）"
    if status == "removed":
        return "已移出列表（文件仍在原位置）"
    if status == "missing":
        return "文件已从磁盘消失"
    if v.get("selected"):
        return "保留（已选定）"
    if total_versions > 1:
        return "在库（未选定）"
    return "在库"


def _render_version(idx: int, total: int, v: dict, prev: dict | None) -> str:
    lines: list[str] = []
    label = v.get("model") or "未知模型"
    tags = _status_label(v, total)
    lines.append(f"### v{idx} · {tags} · {label}")
    lines.append("")

    # 文件位置：优先归档副本，其次原始路径
    archived = v.get("archived_as")
    origin = f"`{v.get('file_path') or v.get('file_name') or '?'}`"
    status = v.get("status") or "active"
    if archived:
        origin_note = "（原位置已删除）" if status == "deleted" else "（原位置仍在磁盘）"
        lines.append(f"- 文件：`{archived}` · 原位置 {origin}{origin_note}")
    elif status == "active":
        lines.append(f"- 文件：{origin}（未复制归档副本，仍在素材目录）")
    else:
        lines.append(f"- 文件：{origin}（未复制归档副本）")

    dims = f"{v.get('width') or '?'}×{v.get('height') or '?'}"
    dur = f"{v.get('duration'):.1f}s" if isinstance(v.get("duration"), (int, float)) else "时长未知"
    lines.append(f"- 规格：{dims} · {dur} · {_human_size(v.get('size'))} · 生成时间（近似）{_fmt_ts(v.get('mtime'))}")

    if prev and prev.get("revised_prompt"):
        lines.append(f"- 生成提示词：承接 v{idx - 1} 精修提示词（推断）＋ 分镜底稿（见上）")
    else:
        lines.append("- 生成提示词：分镜底稿（见上）")

    if v.get("score") is not None:
        when = _fmt_iso(v.get("reviewed_at") or v.get("updated_at"))
        lines.append(f"- 评分：**{v['score']}（{_verdict_label(v.get('score'))}）** · {when} 评定".rstrip())
    else:
        lines.append("- 评分：未评分（待审）")

    lines.append(f"- 存在的问题 / 修改意见：\n{_quote(v.get('feedback'))}")
    lines.append(f"- 修改指引（精修提示词）：\n{_fence_text(v.get('revised_prompt'))}")

    if idx < total:
        tail = "（其生成提示词承接本版精修提示词，若已填写）" if v.get("revised_prompt") else ""
        lines.append(f"- 修改后版本：v{idx + 1}{tail}")
    lines.append("")
    return "\n".join(lines)


def _write_entry(
    session: "ShotReviewSession",
    session_dir: Path,
    episode: str | None,
    shot_id: str,
    group_items: list["ShotReviewItem"],
    overrides: list[dict] | None = None,
) -> None:
    """重写单个镜号的 entry.md：当前库内版本 + 缓存中的历史版本 + 状态覆盖。"""
    shot_dir = _shot_dir(session_dir, episode, shot_id)
    entry_path = shot_dir / "entry.md"
    cached_shot, versions_by_id = _load_cache(entry_path)
    shot_meta = dict(cached_shot)

    for it in group_items:
        v = dict(versions_by_id.get(it.id, {}))
        v.update(_version_from_item(it))
        v["status"] = "active"
        versions_by_id[it.id] = v
    _merge_shot_meta(shot_meta, group_items)

    for ov in overrides or []:
        item_id = ov.get("item_id")
        if not item_id:
            continue
        v = dict(versions_by_id.get(item_id, {}))
        v.update(ov)
        versions_by_id[item_id] = v

    # 库内已不存在且无覆盖的 active 版本 → 标记为磁盘状态未知
    live_ids = {it.id for it in group_items}
    overridden_ids = {ov.get("item_id") for ov in overrides or []}
    for item_id, v in versions_by_id.items():
        if (v.get("status") or "active") == "active" and item_id not in live_ids and item_id not in overridden_ids:
            v["status"] = "missing"

    ordered = sorted(versions_by_id.values(), key=_version_sort_key)
    total = len(ordered)

    # 镜头级元信息：优先取库内条目，其次缓存
    ref_item = group_items[0] if group_items else None
    title_line = shot_id
    func = (ref_item.shot_function if ref_item else None) or shot_meta.get("shot_function")
    if func:
        title_line = f"{shot_id} · {func}"

    final_v = next((v for v in reversed(ordered) if v.get("selected")), None)
    if final_v is None:
        final_v = next((v for v in reversed(ordered) if v.get("score") is not None), None)
    final_score = final_v.get("score") if final_v else None

    body: list[str] = []
    body.append("---")
    body.append(_yaml_line("session_id", session.id))
    body.append(_yaml_line("session", session.title))
    body.append(_yaml_line("episode", episode))
    body.append(_yaml_line("shot_id", shot_id))
    for key in ("shot_function", "shot_size", "movement", "dialogue"):
        body.append(_yaml_line(key, shot_meta.get(key)))
    body.append(_yaml_line("script_duration_s", shot_meta.get("script_duration")))
    body.append(_yaml_line("source_prompt", shot_meta.get("source_prompt")))
    body.append(_yaml_line("versions", total))
    body.append(_yaml_line("final_score", final_score))
    body.append(_yaml_line("final_verdict", _verdict_of(final_score)))
    body.append(_yaml_line("updated_at", now_iso()))
    body.append("---")
    body.append("")
    body.append(f"# {title_line}")
    body.append("")
    body.append(
        f"- 会话：[{session.title}](../../session.md)"
        + (f" · 集 {episode}" if episode else "")
        + (f" · 镜 {_SHOT_NO_RE.search(shot_id).group(1)}" if _SHOT_NO_RE.search(shot_id) else "")
    )
    meta_bits = []
    if shot_meta.get("shot_size"):
        meta_bits.append(f"景别 {shot_meta['shot_size']}")
    if shot_meta.get("movement"):
        meta_bits.append(f"运镜 {shot_meta['movement']}")
    if shot_meta.get("dialogue"):
        meta_bits.append(f"台词 {shot_meta['dialogue']}")
    if shot_meta.get("script_duration") is not None:
        meta_bits.append(f"分镜时长 {shot_meta['script_duration']}s")
    if meta_bits:
        body.append("- " + " · ".join(meta_bits))
    body.append(f"- 版本数：{total}" + (f" · 最终结果：**{final_score}（{_verdict_label(final_score)}）**" if final_score is not None else ""))
    body.append("")
    if shot_meta.get("source_prompt"):
        body.append("## 分镜底稿提示词（本镜共用）")
        body.append("")
        body.append(_fence_text(shot_meta.get("source_prompt")))
        body.append("")
    else:
        body.append("## 分镜底稿提示词（本镜共用）")
        body.append("")
        body.append("（未关联到 shots.md 分镜底稿）")
        body.append("")
    body.append("## 版本链")
    body.append("")
    for i, v in enumerate(ordered):
        body.append(_render_version(i + 1, total, v, ordered[i - 1] if i > 0 else None))
    body.append("---")
    body.append("")
    body.append(f"> 审阅数据由镜头审片自动归档（{now_iso()}），原始素材路径以会话根目录 `{session.root_path}` 为基准。")
    body.append("")

    content = "\n".join(body) + _dump_cache(shot_meta, ordered) + "\n"
    _atomic_write(entry_path, content)


# ---------------- 公开 API（全部不抛异常） ----------------

def sync_shots(session: "ShotReviewSession", items: list["ShotReviewItem"]) -> None:
    """审阅动作（打分/意见/精修提示词/选定）后，重写涉及镜号的 entry.md。"""
    if not _enabled() or session is None or not items:
        return
    try:
        session_dir = _session_dir(session, create=True)
        keys: dict[tuple[str, str], None] = {}
        for it in items:
            keys.setdefault(_group_key(it), None)
        for episode, shot_id in keys:
            group = [x for x in session.items if _group_key(x) == (episode, shot_id)]
            _write_entry(session, session_dir, episode or None, shot_id, group)
    except Exception as e:  # noqa: BLE001 —— 归档绝不影响审片主流程
        logger.warning("审片归档更新失败 session=%s: %s", getattr(session, "id", "?"), e)


def missing_override(item: "ShotReviewItem") -> dict:
    """扫描发现文件从磁盘消失时，为该版本生成状态覆盖（在 db.delete 之前调用）。"""
    try:
        return {
            "item_id": item.id,
            "episode": item.episode,
            "shot_id": item.shot_id,
            "status": "missing",
            "updated_at": now_iso(),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("审片归档 missing_override 失败: %s", e)
        return {}


def rescue_before_delete(item: "ShotReviewItem", delete_file: bool) -> dict:
    """删除条目前抢救数据：复制媒体副本、捕获 mtime。返回交给缓存的覆盖字段。

    在 _delete_item_file 之前调用（文件删除后无法复制）。
    """
    if not _enabled():
        return {}
    try:
        session = item.session
        if session is None:
            return {}
        override: dict = {
            "item_id": item.id,
            "episode": item.episode,
            "shot_id": item.shot_id,
            "status": "deleted" if delete_file else "removed",
            "deleted_at": now_iso(),
            "updated_at": now_iso(),
        }
        if delete_file:
            abs_file = _item_abs_file(item)
            if abs_file is not None:
                try:
                    override["mtime"] = abs_file.stat().st_mtime
                except OSError:
                    pass
                session_dir = _session_dir(session, create=True)
                media_dir = _shot_dir(session_dir, item.episode, item.shot_id) / "media"
                ref = _archive_media_copy(item.id, item.file_name, abs_file, media_dir)
                if ref:
                    override["archived_as"] = ref
        return override
    except Exception as e:  # noqa: BLE001
        logger.warning("审片归档删前抢救失败 item=%s: %s", getattr(item, "id", "?"), e)
        return {}


def apply_delete_overrides(db: "DBSession", session: "ShotReviewSession", overrides: list[dict]) -> None:
    """版本删除/移出后：把状态覆盖写入对应 entry.md 并刷新会话索引。"""
    if not _enabled() or session is None or not overrides:
        return
    try:
        session_dir = _session_dir(session, create=True)
        by_shot: dict[tuple[str, str], list[dict]] = {}
        for ov in overrides:
            key = (ov.get("episode") or "", ov.get("shot_id") or "S??")
            by_shot.setdefault(key, []).append(ov)
        for (episode, shot_id), shot_overrides in by_shot.items():
            group = [x for x in session.items if _group_key(x) == (episode, shot_id)]
            _write_entry(session, session_dir, episode or None, shot_id, group, overrides=shot_overrides)
        _write_session_md(session, session_dir)
        _write_index(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("审片归档删除同步失败 session=%s: %s", getattr(session, "id", "?"), e)


def after_scan(
    db: "DBSession",
    session: "ShotReviewSession",
    touched: list[tuple[str | None, str | None]],
    overrides: list[dict] | None = None,
) -> None:
    """扫描（创建会话/重新扫描）后：为涉及镜号建档，刷新 session.md 与全局索引。"""
    if not _enabled() or session is None:
        return
    try:
        session_dir = _session_dir(session, create=True)
        by_shot: dict[tuple[str, str], list[dict]] = {}
        for ov in overrides or []:
            key = (ov.get("episode") or "", ov.get("shot_id") or "S??")
            by_shot.setdefault(key, []).append(ov)
        keys: list[tuple[str, str]] = []
        for episode, shot_id in touched:
            key = (episode or "", shot_id or "S??")
            if key not in by_shot:
                by_shot.setdefault(key, [])
            if key not in keys:
                keys.append(key)
        for (episode, shot_id), shot_overrides in by_shot.items():
            group = [x for x in session.items if _group_key(x) == (episode, shot_id)]
            _write_entry(session, session_dir, episode or None, shot_id, group, overrides=shot_overrides)
        _write_session_md(session, session_dir)
        _write_index(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("审片归档扫描同步失败 session=%s: %s", getattr(session, "id", "?"), e)


def finalize_session(db: "DBSession", session: "ShotReviewSession") -> None:
    """会话标记完成：归档每镜「原始版本（首版本）」与「最终保留版本（选定/最高分）」
    的媒体副本，全量刷新 entry / session.md / INDEX.md。"""
    if not _enabled() or session is None:
        return
    try:
        session_dir = _session_dir(session, create=True)
        groups: dict[tuple[str, str], list["ShotReviewItem"]] = {}
        for it in session.items:
            groups.setdefault(_group_key(it), []).append(it)

        for (episode, shot_id), items in groups.items():
            # 链首（原内容）与最终版本（修改后内容）——同一版本只复制一次
            chain = sorted(
                items,
                key=lambda it: (_item_mtime(it) or math.inf, it.file_name),
            )
            first = chain[0]
            selected = next((i for i in chain if i.selected), None)
            scored = [i for i in chain if i.score is not None]
            if selected is not None:
                chosen = selected
            elif scored:
                chosen = max(scored, key=lambda i: (i.score, _item_mtime(i) or 0.0))
            else:
                chosen = chain[-1]
            entry_overrides: list[dict] = []
            entry_path = _shot_dir(session_dir, episode, shot_id) / "entry.md"
            _, versions_by_id = _load_cache(entry_path)
            for target in {first.id: first, chosen.id: chosen}.values():
                ref = _ensure_archived(session, session_dir, target, versions_by_id.get(target.id))
                if ref:
                    entry_overrides.append(
                        {"item_id": target.id, "archived_as": ref, "updated_at": now_iso()}
                    )
            _write_entry(session, session_dir, episode or None, shot_id, items, overrides=entry_overrides)

        _write_session_md(session, session_dir)
        _write_index(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("审片归档完成归档失败 session=%s: %s", getattr(session, "id", "?"), e)


def refresh_index(db: "DBSession") -> None:
    """重建全局 INDEX.md（会话创建/改名/删除后调用；删除的会话档案保留并标记）。"""
    if not _enabled():
        return
    try:
        _write_index(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("审片归档索引刷新失败: %s", e)


# ---------------- session.md / INDEX.md ----------------

def _write_session_md(session: "ShotReviewSession", session_dir: Path) -> None:
    try:
        summary = json.loads(session.summary_json or "{}")
    except json.JSONDecodeError:
        summary = {}

    groups: dict[tuple[str, str], list["ShotReviewItem"]] = {}
    for it in session.items:
        groups.setdefault(_group_key(it), []).append(it)

    rows: list[str] = []
    for (episode, shot_id), items in sorted(
        groups.items(), key=lambda kv: (kv[0][0], _shot_no_of(kv[0][1]), kv[0][1])
    ):
        def _rev_key(i: "ShotReviewItem") -> str:
            return i.reviewed_at or i.updated_at or ""

        scored_sorted = sorted([i for i in items if i.score is not None], key=_rev_key)
        first = scored_sorted[0] if scored_sorted else None
        chosen = next((i for i in items if i.selected), None) or (scored_sorted[-1] if scored_sorted else None)

        first_txt = f"{first.score}（{_verdict_label(first.score)}）" if first else "—"
        final_txt = f"{chosen.score}（{_verdict_label(chosen.score)}）" if chosen else "—"
        result = _verdict_label(chosen.score) if chosen and chosen.score is not None else VERDICT_LABELS["pending"]
        rel = f"{_safe_component(episode or _UNPARSED_EPISODE)}/{_safe_component(shot_id)}/entry.md"
        rows.append(
            f"| {shot_id} | {len(items)} | {first_txt} | {final_txt} | {result} | [entry]({rel}) |"
        )

    lines = [
        "---",
        _yaml_line("session_id", session.id),
        _yaml_line("title", session.title),
        _yaml_line("root_path", session.root_path),
        _yaml_line("status", session.status),
        _yaml_line("status_label", SESSION_STATUS_LABELS.get(session.status, session.status)),
        _yaml_line("total", summary.get("total")),
        _yaml_line("scored", summary.get("scored")),
        _yaml_line("average_score", summary.get("average_score")),
        _yaml_line("multi_take_shots", summary.get("multi_take_shots")),
        _yaml_line("selected_shots", summary.get("selected_shots")),
        _yaml_line("created_at", session.created_at),
        _yaml_line("updated_at", session.updated_at),
        _yaml_line("index_generated_at", now_iso()),
        "---",
        "",
        f"# {session.title} · 审片档案",
        "",
        f"- 素材根目录：`{session.root_path}`",
        f"- 状态：{SESSION_STATUS_LABELS.get(session.status, session.status)}"
        f" · 镜头 {summary.get('total', 0)} · 已评 {summary.get('scored', 0)}"
        f" · 均分 {summary.get('average_score') if summary.get('average_score') is not None else '--'}",
        f"- 创建 {_fmt_iso(session.created_at)} · 最近更新 {_fmt_iso(session.updated_at)}",
        "",
        "> 「首评 / 终评」按评分时间推断；完整版本链（含已清理的废弃版本与媒体副本）见各镜号 entry.md。",
        "> 本文件在扫描 / 清理版本 / 标记完成时自动刷新，最新逐镜明细以 entry.md 为准。",
        "",
        "## 镜号索引",
        "",
        "| 镜号 | 版本数 | 首评 | 终评 | 结果 | 档案 |",
        "| --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
        f"返回全局索引：[INDEX.md](../INDEX.md)",
        "",
    ]
    _atomic_write(session_dir / "session.md", "\n".join(lines))


def _write_index(db: "DBSession") -> None:
    from .shot_review_service import list_sessions

    root = _archive_root()
    sessions = list_sessions(db)
    live_id8 = {s.id[:8] for s in sessions}

    rows: list[str] = []
    for s in sessions:
        try:
            summary = json.loads(s.summary_json or "{}")
        except json.JSONDecodeError:
            summary = {}
        folder = _session_dir(s, create=False)
        rows.append(
            f"| [{s.title}]({folder.name}/session.md) | `{s.root_path}`"
            f" | {summary.get('total', '-')} | {summary.get('average_score') if summary.get('average_score') is not None else '--'}"
            f" | {SESSION_STATUS_LABELS.get(s.status, s.status)} | {_fmt_iso(s.updated_at)} |"
        )

    leftover_rows: list[str] = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if any(child.name.endswith(f"-{i}") for i in live_id8):
                continue
            leftover_rows.append(
                f"| [{child.name}]({child.name}/session.md) | — | — | — | 会话已删除，档案保留 | — |"
            )

    lines = [
        "# 镜头审片数据档案",
        "",
        f"> 由镜头审片自动沉淀（生成时间 {now_iso()}）：记录每个镜号「原内容 → 评分 → 存在的问题 →"
        " 修改指引 → 修改后内容」的完整迭代链，供优化 AI 工作流与提示词参考。",
        "",
        "## 会话索引",
        "",
        "| 会话 | 素材根目录 | 镜头数 | 均分 | 状态 | 更新时间 |",
        "| --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
    ]
    if leftover_rows:
        lines += [
            "## 已删除会话的留存档案",
            "",
            "| 文件夹 | 素材根目录 | 镜头数 | 均分 | 状态 | 更新时间 |",
            "| --- | --- | --- | --- | --- | --- |",
            *leftover_rows,
            "",
        ]
    _atomic_write(root / "INDEX.md", "\n".join(lines))
