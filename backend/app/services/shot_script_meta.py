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

"""分镜信息解析：把剧集目录里的 shots.md 与生成报告解析为镜头元信息。

用途：镜头审片时把「该镜应有什么」（分镜脚本定义）与「实际生成了什么」
（成片报告）并排呈现，供制片人对照打分。

只读取真实存在的字段，缺失一律如实返回 None，绝不臆造。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# 集号目录名（EP01 / EP12 …）
EPISODE_DIR_RE = re.compile(r"^EP\d+$", re.I)
# 镜号全称（EP07-S01）
FULL_SHOT_RE = re.compile(r"EP(\d+)[-_]S(\d+)", re.I)
# 裸镜号（S01）——前置不能是字母，避免误匹配 uuid / seedance 等
BARE_SHOT_RE = re.compile(r"(?<![A-Za-z])S(\d+)")
# shots.md 小节标题与总览表首列
SHOT_HEADING_RE = re.compile(r"^##\s+(EP\d+-S\d+)\s*$", re.I)
OVERVIEW_ID_RE = re.compile(r"^EP\d+-S\d+$", re.I)
# 台词行：台词："English verbatim."
DIALOGUE_RE = re.compile(r"台词[：:]\s*[\"“](.+?)[\"”]")

# 组成视频生成提示词的 shots.md 字段行（人物外观 / 场景锚点 / 动作 / 光感等），
# 提取原文拼接为该镜的提示词底稿，供审片人在其基础上改写精修提示词。
PROMPT_FIELD_RE = re.compile(r"^\*\*(人物|场景描述|台词同步|光感|色调|构图|细节)[：:]", re.I)
MOTION_TITLE_PREFIX = "**秒级动作拆解"

# 向上查找 shots.md 的最大层数（EPxx/video_renders/Sxx/ 最多 3 层）
_ANCESTOR_DEPTH = 6


def normalize_shot_no(shot_id: str | None) -> str | None:
    """任意形态的镜号（S1 / S01 / EP07-S01）→ 统一为 S01。"""
    m = BARE_SHOT_RE.search(shot_id or "")
    return f"S{int(m.group(1)):02d}" if m else None


def parse_shot_key(*texts: str | None) -> tuple[str | None, str | None]:
    """从路径片段/文件名解析 (集号 EP07, 镜号 S01)；解析不到的部分为 None。"""
    for text in texts:
        if not text:
            continue
        m = FULL_SHOT_RE.search(text)
        if m:
            return f"EP{int(m.group(1)):02d}", f"S{int(m.group(2)):02d}"
    for text in texts:
        if not text:
            continue
        m = BARE_SHOT_RE.search(text)
        if m:
            return None, f"S{int(m.group(1)):02d}"
    return None, None


def find_episode_dir(rel_parts: list[str]) -> str | None:
    """从相对路径片段里找集号目录名（EP05）。"""
    for part in rel_parts:
        if EPISODE_DIR_RE.match(part):
            return part.upper()
    return None


def locate_script_dir(abs_file: Path, boundary: Path) -> Path | None:
    """向上查找包含 shots.md 的剧集目录（不超过 boundary）。找不到返回 None。"""
    try:
        boundary = boundary.resolve()
    except OSError:
        return None
    current = abs_file.parent
    for _ in range(_ANCESTOR_DEPTH):
        if (current / "shots.md").is_file():
            return current
        try:
            if current.resolve() == boundary:
                return None
        except OSError:
            return None
        if current.parent == current:
            return None
        current = current.parent
    return None


def parse_shots_md(path: Path) -> dict[str, dict]:
    """shots.md → {归一化镜号 S01: {shot_function, script_duration, shot_size, angle, movement, dialogue, prompt_source}}。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    meta: dict[str, dict] = {}
    current: dict | None = None
    # 秒级动作拆解小节内的 bullet 行也属于提示词底稿，进入该小节后开始收集
    in_motion = False

    def slot(shot_no: str) -> dict:
        return meta.setdefault(shot_no, {
            "shot_function": None, "script_duration": None, "shot_size": None,
            "angle": None, "movement": None, "dialogue": None, "prompt_source": None,
        })

    for line in lines:
        # 总览表：| EP05-S01 | 4 | wide | high-angle | slow-tilt-down | … |
        if line.startswith("| EP") and line.count("|") >= 15:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and OVERVIEW_ID_RE.match(cells[0]):
                shot_no = normalize_shot_no(cells[0])
                if shot_no:
                    entry = slot(shot_no)
                    entry["script_duration"] = _as_float(cells[1])
                    entry["shot_size"] = cells[2] or None
                    entry["angle"] = cells[3] or None
                    entry["movement"] = cells[4] or None
            continue

        heading = SHOT_HEADING_RE.match(line)
        if heading:
            shot_no = normalize_shot_no(heading.group(1))
            current = slot(shot_no) if shot_no else None
            in_motion = False
            continue

        if current is None:
            continue
        if line.startswith("**镜头功能："):
            current["shot_function"] = line.split("：", 1)[1].lstrip("*").strip() or None
        if "台词" in line:
            found = DIALOGUE_RE.findall(line)
            if found:
                text = " / ".join(part.strip() for part in found if part.strip())
                current["dialogue"] = text or None

        # 提示词底稿：按 shots.md 原文收集生成该镜所需字段（人物/场景/动作/光感…）
        if line.startswith(MOTION_TITLE_PREFIX):
            in_motion = True
        elif line.startswith("**"):
            in_motion = False
            if PROMPT_FIELD_RE.match(line):
                current.setdefault("_prompt_lines", []).append(line)
        elif in_motion and line.startswith("- "):
            current.setdefault("_prompt_lines", []).append(line)

    for entry in meta.values():
        collected = entry.pop("_prompt_lines", None) or []
        entry["prompt_source"] = "\n".join(collected).strip() or None
    return meta


def parse_generation_report(video_renders_dir: Path) -> dict[str, dict]:
    """生成报告/生产清单 → {归一化镜号 S01: {render_status, model, render_duration_s}}。"""
    rows: list[dict] = []
    report = _first_existing(video_renders_dir.glob("generation_report*.json"))
    if report is not None:
        rows = _read_json(report).get("results") or []
    if not rows:
        manifest = video_renders_dir / "production_manifest.json"
        if manifest.is_file():
            rows = _read_json(manifest).get("shots") or []

    result: dict[str, dict] = {}
    for row in rows:
        shot_no = normalize_shot_no(row.get("shot_id"))
        if not shot_no:
            continue
        result[shot_no] = {
            "render_status": row.get("status") or None,
            "model": row.get("model") or None,
            "render_duration_s": _as_float(
                row.get("render_duration_s") or row.get("duration_s")
            ),
        }
    return result


def load_episode_meta(script_dir: Path) -> dict[str, dict]:
    """读取一个剧集目录的全部镜头元信息，键为归一化镜号 S01。

    分镜信息取自 shots.md，生成状态取自 video_renders/ 下的报告；两者均缺失时返回空表。
    """
    meta = parse_shots_md(script_dir / "shots.md")
    report = parse_generation_report(script_dir / "video_renders")
    for shot_no, entry in report.items():
        target = meta.setdefault(shot_no, {
            "shot_function": None, "script_duration": None, "shot_size": None,
            "angle": None, "movement": None, "dialogue": None, "prompt_source": None,
        })
        target.update(entry)
    return meta


def _first_existing(paths) -> Path | None:
    for path in sorted(paths):
        if path.is_file():
            return path
    return None


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _as_float(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None