"""新项目脚手架：生成标准短剧项目目录骨架与模板文件。

用法：opendreamina drama init <项目路径> --title <剧名> [--code OLYMPUS] [--episodes 40]

原则：绝不覆盖已有文件——目标路径下已存在的同名文件一律跳过并在结果中标注 skipped，
可重复执行补齐缺失文件。
"""

from __future__ import annotations

import json
from pathlib import Path

from drama.compiler.maps_template import MAPS_TEMPLATE
from drama.scaffold import templates

# 标准目录树（审阅系统零配置对接：项目根放在 data/review_sources/ 下即可被扫描）
DIRECTORY_TREE = (
    "分集剧本",
    "分镜脚本",
    "素材库/01_characters",
    "素材库/02_scenes",
    "素材库/03_props/props",
    "素材库/04_iconic_scenes",
    "素材库/05_index",
    "素材库/06_bgm",
    "素材库/06_voiceover",
    "参考素材",
    "成片",
    "qc_frames",
    "tools/episode_specs",
)

DEFAULT_AESTHETIC = "1990s television drama production still, film grain, painterly realism"


def create_project(path: str | Path, *, title: str = "", code: str = "",
                   episodes: int = 40, duration: int = 90, language: str = "中文",
                   aesthetic: str = DEFAULT_AESTHETIC) -> dict:
    """在 path 创建项目骨架，返回 {project_root, created[], skipped[]}。"""
    root = Path(path).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise SystemExit(f"目标路径已存在且不是目录：{root}")
    root.mkdir(parents=True, exist_ok=True)

    title = title or root.name
    code = code or root.name
    fill = {
        "{{TITLE}}": title,
        "{{CODE}}": code,
        "{{EPISODES}}": str(episodes),
        "{{DURATION}}": str(duration),
        "{{LANGUAGE}}": language,
        "{{AESTHETIC}}": aesthetic,
        "{{SHOTS}}": "18",
        "{{EP}}": "EP01",
    }

    created: list[str] = []
    skipped: list[str] = []

    def _write(rel: str, content: str) -> None:
        target = root / rel
        if target.exists():
            skipped.append(rel)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created.append(rel)

    for directory in DIRECTORY_TREE:
        target = root / directory
        if target.exists():
            continue
        target.mkdir(parents=True, exist_ok=True)
        created.append(directory + "/")

    _write("目标设定.md", _fill(templates.GOAL_TEMPLATE, fill))
    _write("工作流程和注意事项.md", _fill(templates.WORKFLOW_TEMPLATE, fill))
    _write("剧本大纲.md", _fill(templates.OUTLINE_TEMPLATE, fill))
    _write("分镜脚本/_SPEC_分镜模板规范.md", _fill(templates.SPEC_DOC_TEMPLATE, fill))
    _write("分镜脚本/EP01/shots.md", _fill(templates.SHOTS_TEMPLATE, fill))
    _write("tools/maps.py", MAPS_TEMPLATE)

    manifest = dict(templates.MANIFEST_TEMPLATE)
    manifest["project"] = title
    _write("tools/assets_manifest.json",
           json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    voice = dict(templates.VOICE_MANIFEST_TEMPLATE)
    voice["project"] = title
    _write("tools/voice_manifest.json",
           json.dumps(voice, ensure_ascii=False, indent=2) + "\n")
    _write("tools/asset_registry.json",
           json.dumps(templates.ASSET_REGISTRY_TEMPLATE, ensure_ascii=False, indent=2) + "\n")

    return {
        "project_root": str(root),
        "title": title,
        "next_steps": [
            "填写 目标设定.md 与 剧本大纲.md（人工确认）",
            "写分集剧本（分集剧本/），再拆分镜（分镜脚本/EP01/shots.md）",
            "opendreamina drama lint EP01 --project .   校验分镜格式",
            "opendreamina drama compile EP01 --project .  编译英文提示词",
            "opendreamina drama spec EP01 --project . --write  生成分集执行规格",
            "项目根放入 data/review_sources/ 后，审阅中心即可扫描（素材审阅 + 镜头审片）",
        ],
        "created": created,
        "skipped": skipped,
    }


def _fill(template: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        template = template.replace(key, value)
    return template
