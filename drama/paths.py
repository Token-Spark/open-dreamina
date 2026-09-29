"""项目路径解析：把「短剧项目根目录」的约定子路径集中在一处。

标准目录结构（`opendreamina drama init` 生成，详见 drama/README.md）：

    {project_root}/
    ├── 分镜脚本/EPxx/shots.md          # 第3级：逐镜头分镜（唯一权威数据源）
    │   └── EPxx/video_renders/         # 生成结果（按镜号子目录）
    ├── 素材库/01_characters/…06_voiceover/
    └── tools/                          # 项目级数据（manifest / episode_specs / maps.py）

项目根的解析优先级：--project 参数 > 环境变量 DRAMA_PROJECT_ROOT > 当前工作目录。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

EPISODE_DIR_RE = re.compile(r"^EP\d+$", re.IGNORECASE)


def resolve_project_root(explicit: str | None = None) -> Path:
    """解析项目根目录：显式参数 > 环境变量 > 当前目录。"""
    raw = explicit or os.environ.get("DRAMA_PROJECT_ROOT") or "."
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"项目根目录不存在：{root}")
    return root


def normalize_episode(raw: str) -> str:
    """集号归一：5 / 05 / ep05 → EP05。"""
    text = (raw or "").strip().upper()
    match = re.match(r"^(?:EP)?(\d+)$", text)
    if not match:
        raise SystemExit(f"集号格式不合法：{raw!r}（应为 EP05 / 05 / 5）")
    return f"EP{int(match.group(1)):02d}"


def shots_dir(project_root: Path) -> Path:
    return project_root / "分镜脚本"


def episode_dir(project_root: Path, episode: str) -> Path:
    return shots_dir(project_root) / episode


def shots_md_path(project_root: Path, episode: str) -> Path:
    return episode_dir(project_root, episode) / "shots.md"


def video_renders_dir(project_root: Path, episode: str) -> Path:
    return episode_dir(project_root, episode) / "video_renders"


def asset_library_dir(project_root: Path) -> Path:
    return project_root / "素材库"


def asset_index_dir(project_root: Path) -> Path:
    return asset_library_dir(project_root) / "05_index"


def tools_dir(project_root: Path) -> Path:
    return project_root / "tools"


def episode_specs_dir(project_root: Path) -> Path:
    return tools_dir(project_root) / "episode_specs"


def maps_path(project_root: Path) -> Path:
    """项目级中英映射表（可选；存在时自动加载，详见 drama.compiler.maps_template）。"""
    return tools_dir(project_root) / "maps.py"


def list_episodes(project_root: Path) -> list[dict]:
    """扫描 分镜脚本/ 下的集目录，返回 [{episode, shots_md, video_renders}]。

    只认 `EPxx` 目录名；缺 shots.md 的目录照常列出（shots_md=False），
    便于 list / lint 提示补齐。
    """
    root = shots_dir(project_root)
    if not root.is_dir():
        return []
    episodes: list[dict] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not EPISODE_DIR_RE.match(child.name):
            continue
        episodes.append({
            "episode": child.name.upper(),
            "shots_md": (child / "shots.md").is_file(),
            "video_renders": (child / "video_renders").is_dir(),
        })
    return episodes
