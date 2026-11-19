"""把外部短剧项目的分镜与生成结果整理为审片中心的导入清单。

纯本地只读：只解析项目里的文件，不写任何东西。落库由调用方通过
``POST /shot-reviews/sessions/{id}/items/import`` 完成。

数据来源（缺哪个就如实留空，绝不臆造）：

    {项目}/02_分镜脚本/EPxx_分镜.md        逐镜表 → 分镜「应有」（秒数/景别/运镜/画面/台词）
    {项目}/08_成片制作/state/EPxx.json     生产状态 → 每镜所属生成任务与实测时长
    {项目}/08_成片制作/EPxx/video_renders/Sxx_*/EPxx-Sxx.mp4   成片镜头（导入对象）
    GET /tasks/{task_id}                   生成任务详情 → 提示词/模型/状态

兼容两种项目布局：本项目这种「02_分镜脚本 + 08_成片制作」的编号目录，以及
``drama init`` 生成的「分镜脚本/EPxx/shots.md + EPxx/video_renders」标准骨架。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

EPISODE_RE = re.compile(r"^EP(\d+)$", re.IGNORECASE)
# 文件名里的整镜号（EP01-S03），用来把视频文件对回镜号
SHOT_FILE_RE = re.compile(r"(EP\d+)[-_]S(\d+)", re.IGNORECASE)
# 逐镜表里的裸镜号（S01）
BARE_SHOT_RE = re.compile(r"^S(\d+)$", re.IGNORECASE)
# 分镜表里「景别·机位·焦段·运动」的运镜词：运动描述总在末段
_MOVEMENT_RE = re.compile(
    r"(固定|微推|推|缓推|拉|缓拉|摇|移|跟|升|降|环绕|手持|甩|变焦|俯冲|升降|旋转)"
)

# 逐镜表列 → 字段的识别关键字（表头写法允许有差异）
_HEADER_KEYS = (
    ("shot", ("镜号", "镜头号", "shot")),
    ("duration", ("秒数", "时长", "duration")),
    ("beat", ("场/节拍", "节拍", "场景/节拍", "beat")),
    ("framing", ("景别", "机位", "焦段", "构图")),
    ("action", ("画面", "动作", "description")),
    ("dialogue", ("对白", "台词", "dialogue")),
)


# ---------------- 表格解析 ----------------


def _split_row(line: str) -> list[str]:
    """拆分 markdown 表格行，返回去掉首尾竖线后的单元格（保留内部空白原样）。"""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip() for cell in body.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def _map_headers(cells: list[str]) -> dict[str, int]:
    """表头 → 列索引。只认明确命中的关键字，认不出的列忽略。"""
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(cells):
        text = cell.lower()
        for field, keywords in _HEADER_KEYS:
            if field in mapping:
                continue
            if any(k.lower() in text for k in keywords):
                mapping[field] = idx
                break
    return mapping


def parse_storyboard(md_path: Path) -> dict[str, dict]:
    """解析分镜脚本的逐镜表 → {镜号 S01: {duration, beat, framing, action, dialogue}}。

    只认第一张表头同时含「镜号」与「秒数/时长」的表格；同文件里其它表格
    （场次表、资产表等）跳过。空单元格返回 None，不补默认值。
    """
    try:
        lines = md_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    shots: dict[str, dict] = {}
    columns: dict[str, int] | None = None
    for line in lines:
        if not line.lstrip().startswith("|"):
            # 逐镜表结束：只认第一张表，后面的资产表/校验表不再解析
            if columns is not None and shots:
                break
            continue
        cells = _split_row(line)
        if columns is None:
            candidate = _map_headers(cells)
            if "shot" in candidate and ("duration" in candidate or "framing" in candidate):
                columns = candidate
            continue
        if _is_separator(cells):
            continue
        if columns.get("shot", 0) >= len(cells):
            continue

        shot_cell = cells[columns["shot"]]
        match = BARE_SHOT_RE.match(shot_cell) or re.search(r"S(\d+)", shot_cell, re.IGNORECASE)
        if not match:
            continue
        shot_no = f"S{int(match.group(1)):02d}"

        def cell(field: str) -> str | None:
            idx = columns.get(field)
            if idx is None or idx >= len(cells):
                return None
            value = cells[idx].strip()
            return value or None

        shots[shot_no] = {
            "duration": _as_float(cell("duration")),
            "beat": cell("beat"),
            "framing": cell("framing"),
            "action": cell("action"),
            "dialogue": _clean_dialogue(cell("dialogue")),
        }
    return shots


def _clean_dialogue(text: str | None) -> str | None:
    """去掉台词前的 D01 编号，保留「角色: 英文 / 中文」原文；占位破折号视为无台词。"""
    if not text:
        return None
    cleaned = re.sub(r"^D\d+\s*", "", text.strip())
    if cleaned in {"—", "——", "-", "–", "无", "/"}:
        return None
    return cleaned or None


def split_framing(framing: str | None) -> tuple[str | None, str | None]:
    """「近景·门厅矮柜平视·50mm·固定」→ (景别 近景, 运镜 固定)。"""
    if not framing:
        return None, None
    parts = [p.strip() for p in re.split(r"[·・/｜|]", framing) if p.strip()]
    if not parts:
        return None, None
    shot_size = parts[0]
    movement = None
    for part in reversed(parts):
        if _MOVEMENT_RE.search(part):
            movement = part
            break
    return shot_size, movement


# ---------------- 生产状态 ----------------


def load_production_state(state_path: Path) -> dict[str, dict]:
    """08_成片制作/state/EPxx.json → {镜号 S01: {tg, task_id, actual, file}}。

    该文件按「连拍组 TGxx」记录：每组一条 frame 任务、一条 clip 任务，
    cut.files 列出本组切出的每一镜（含设计时长与实际时长）。这里把切分结果
    摊平成以镜号为键的表，便于逐镜建立审片卡片与生成任务的对应关系。
    """
    if not state_path.is_file():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    by_shot: dict[str, dict] = {}
    for tg_id, entry in (data.get("items") or {}).items():
        clip = entry.get("clip") or {}
        for row in (entry.get("cut") or {}).get("files") or []:
            shot_no = _normalize_shot(row.get("shot"))
            if not shot_no:
                continue
            by_shot[shot_no] = {
                "tg": tg_id,
                "task_id": clip.get("task_id"),
                "clip_status": clip.get("status"),
                "actual": _as_float(row.get("actual")),
                "designed": _as_float(row.get("designed")),
                "file": row.get("file"),
                "ok": row.get("ok"),
            }
    return by_shot


def _normalize_shot(value) -> str | None:
    match = re.search(r"S(\d+)", str(value or ""), re.IGNORECASE)
    return f"S{int(match.group(1)):02d}" if match else None


# ---------------- 项目布局 ----------------


def _storyboard_candidates(project: Path, episode: str) -> list[Path]:
    return [
        project / "02_分镜脚本" / f"{episode}_分镜.md",
        project / "分镜脚本" / f"{episode}_分镜.md",
        project / "分镜脚本" / episode / "shots.md",
        project / "02_分镜脚本" / episode / "shots.md",
    ]


def _renders_dir_candidates(project: Path, episode: str) -> list[Path]:
    return [
        project / "08_成片制作" / episode / "video_renders",
        project / "分镜脚本" / episode / "video_renders",
        project / "成片" / episode / "video_renders",
    ]


def discover_episodes(project: Path) -> list[dict]:
    """列出有成片镜头目录的集（按集号排序）。

    集目录可能挂在项目根（``drama init`` 骨架）或编号子目录下（如 ``08_成片制作``），
    两个位置都找一遍。分镜表缺失的集照常列出——卡片仍可只凭生成结果建立，
    只是没有「应有」一栏可对照。

    返回 [{episode, storyboard, renders_dir, state}]。
    """
    roots = [project / "08_成片制作", project / "分镜脚本", project]
    found: dict[str, dict] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_dir():
                continue
            match = EPISODE_RE.match(path.name)
            if not match:
                continue
            episode = f"EP{int(match.group(1)):02d}"
            if episode in found:
                continue
            renders = next((p for p in _renders_dir_candidates(project, episode) if p.is_dir()), None)
            if renders is None:
                continue
            found[episode] = {
                "episode": episode,
                "storyboard": next(
                    (p for p in _storyboard_candidates(project, episode) if p.is_file()), None
                ),
                "renders_dir": renders,
                "state": project / "08_成片制作" / "state" / f"{episode}.json",
            }
    return [found[key] for key in sorted(found, key=_shot_sort_key)]


def collect_shot_files(episode: str, renders_dir: Path) -> dict[str, Path]:
    """成片目录 → {镜号 S01: 视频文件}。

    只认文件名里带「EPxx-Sxx」的视频；``_takes``（多镜合拍的母版）与
    以 ``_`` 开头的辅助目录不参与，避免同一镜出现多个候选。
    """
    found: dict[str, Path] = {}
    for candidate in sorted(renders_dir.rglob("*.mp4")):
        rel = candidate.relative_to(renders_dir)
        if any(part.startswith("_") for part in rel.parts[:-1]):
            continue
        match = SHOT_FILE_RE.search(candidate.stem)
        if not match:
            continue
        if match.group(1).upper() != episode:
            continue
        found[f"S{int(match.group(2)):02d}"] = candidate
    return found


# ---------------- 组装导入清单 ----------------


def build_import_rows(
    project: Path,
    *,
    drama_title: str | None = None,
    episodes: list[str] | None = None,
    task_lookup=None,
    include_prompt: bool = True,
) -> dict:
    """组装导入清单。

    - project：项目根目录（宿主机本地路径，用来读文件与拼相对路径）；
    - task_lookup：``(task_id) -> dict | None``，返回生成任务详情（提示词/模型/状态）；
      传 None 或 include_prompt=False 时不查任务，提示词留空；
    - episodes：只导入指定集（EP01/1 均可），缺省导入全部有成片的集。

    返回 {rows, episodes, missing_shots, counts}。missing_shots 记录「分镜有、成片没有」
    的镜号——这本身就是审片要看的缺口，不静默丢弃。
    """
    wanted = {_normalize_episode(e) for e in (episodes or [])} or None
    found = [ep for ep in discover_episodes(project) if wanted is None or ep["episode"] in wanted]

    rows: list[dict] = []
    missing_shots: list[dict] = []
    task_cache: dict[str, dict | None] = {}
    skipped_episodes: list[str] = []

    for entry in found:
        episode = entry["episode"]
        storyboard = parse_storyboard(entry["storyboard"]) if entry.get("storyboard") else {}
        files = collect_shot_files(episode, entry["renders_dir"])
        state = load_production_state(entry["state"])
        if not files:
            skipped_episodes.append(episode)
            continue

        for shot_no in sorted(storyboard or files, key=_shot_sort_key):
            video = files.get(shot_no)
            if video is None:
                missing_shots.append({"episode": episode, "shot_id": f"{episode}-{shot_no}"})
                continue
            shot = storyboard.get(shot_no, {})
            production = state.get(shot_no, {})
            shot_size, movement = split_framing(shot.get("framing"))

            task_id = production.get("task_id")
            task = None
            if include_prompt and task_id and task_lookup is not None:
                if task_id not in task_cache:
                    try:
                        task_cache[task_id] = task_lookup(task_id)
                    except Exception:  # noqa: BLE001 —— 任务查不到不影响建档
                        task_cache[task_id] = None
                task = task_cache[task_id]

            rows.append({
                "episode": episode,
                "shot_id": f"{episode}-{shot_no}",
                "drama_title": drama_title,
                "file_path": str(video.relative_to(project)).replace("\\", "/"),
                "duration": production.get("actual") or shot.get("duration"),
                "script_duration": shot.get("duration") or production.get("designed"),
                "shot_size": shot_size,
                "movement": movement,
                "shot_function": _compose_shot_function(shot, production),
                "dialogue": shot.get("dialogue"),
                "render_status": (task or {}).get("status") or production.get("clip_status") or None,
                "model": (task or {}).get("model_id") or None,
                "source_prompt": _compose_prompt(
                    episode=episode,
                    shot_no=shot_no,
                    shot=shot,
                    production=production,
                    task=task,
                ) if include_prompt else None,
                "input_asset_ids": _extract_input_asset_ids(task),
            })

    counts = {
        "episodes": len({r["episode"] for r in rows}),
        "shots": len(rows),
        "missing_shots": len(missing_shots),
        "skipped_episodes": len(skipped_episodes),
    }
    return {
        "rows": rows,
        "episodes": sorted({r["episode"] for r in rows}),
        "missing_shots": missing_shots,
        "skipped_episodes": skipped_episodes,
        "counts": counts,
    }


def _extract_input_asset_ids(task: dict | None) -> list[str] | None:
    """提取该镜头原生成任务引用的参考素材 id 列表。

    优先 params.input_asset_ids（完整列表，逐项过滤非空字符串）；旧任务只落了
    首张 input_asset_id 时回退为一元素列表；查到有效任务但确实没有参考资产时
    返回空列表（事实，允许写入空）。

    task 为 None（--no-prompt、任务查询失败、include_prompt=False）时返回 None：
    该字段随 row 带入后端后为 None，import_items 的「值非 None 才更新」判断会
    跳过，避免重复导入时把已有参考素材清空造成数据倒退。
    """
    if task is None:
        return None
    params = task.get("params") or {}
    refs = params.get("input_asset_ids") if isinstance(params, dict) else None
    if isinstance(refs, list):
        return [aid for aid in refs if isinstance(aid, str) and aid]
    single = task.get("input_asset_id")
    return [single] if isinstance(single, str) and single else []


def _shot_sort_key(shot_no: str) -> int:
    match = re.search(r"(\d+)", shot_no)
    return int(match.group(1)) if match else 0


def _compose_shot_function(shot: dict, production: dict) -> str | None:
    """卡片标题下那两行：节拍 + 画面动作（分镜「应有」），没有就如实留空。"""
    beat = shot.get("beat")
    action = _strip_markdown(shot.get("action"))
    if beat and action:
        return f"{beat}｜{action}"
    return action or beat or None


def _strip_markdown(text: str | None) -> str | None:
    """去掉强调标记（**同一镜内** → 同一镜内），卡片是纯文本展示。"""
    if not text:
        return None
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).strip() or None


def _compose_prompt(
    *, episode: str, shot_no: str, shot: dict, production: dict, task: dict | None
) -> str | None:
    """提示词底稿：分镜与生成任务的溯源抬头 + 该组连拍任务的实际提示词。

    连拍组用一条提示词合成整段母版再切镜，所以卡片里附上抬头说明本卡属于
    哪个任务、原任务的镜头范围是什么，避免把整段提示词误当成「只生成这一镜」。
    """
    header: list[str] = []
    framing = shot.get("framing")
    duration = shot.get("duration") or production.get("designed")
    meta = " · ".join(
        part for part in (
            f"{episode}-{shot_no}",
            f"{duration}s" if duration else None,
            framing,
            shot.get("beat"),
        ) if part
    )
    if meta:
        header.append(f"【分镜】{meta}")
    tg = production.get("tg")
    task_id = production.get("task_id")
    if tg or task_id:
        trace = " · ".join(part for part in (
            tg,
            f"task {task_id}" if task_id else None,
            (task or {}).get("model_id"),
            "多镜连拍母版切分" if tg else None,
        ) if part)
        header.append(f"【生成任务】{trace}")

    prompt = (task or {}).get("prompt")
    if not header and not prompt:
        return None
    sections = ["\n".join(header)] if header else []
    sections.append(prompt or "（未取到该镜生成任务的提示词，请手动补充）")
    return "\n\n".join(sections)


def _normalize_episode(raw: str) -> str:
    match = re.search(r"(\d+)", str(raw or ""))
    if not match:
        raise ValueError(f"集号格式不合法：{raw!r}（应为 EP05 / 05 / 5）")
    return f"EP{int(match.group(1)):02d}"


def _as_float(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None
