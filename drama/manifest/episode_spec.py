"""分集执行规格（tools/episode_specs/EPxx.json）的生成、校验与读写。

episode_spec 是「数据 / 机制分离」的产物：把每集的素材路径、参考关系、
镜头提示词从生成脚本中抽出，生成器只负责「怎么调平台」。

schema（对齐《代号奥林匹斯》实测数据）：

    {
      "episode": "EP05",
      "episode_name_zh": "第一顿饭 · The First Meal",
      "source_shotlist": "分镜脚本/EP05/shots.md",
      "duration_target_s": 90,
      "generation": {"provider": "...", "model": "...", "aspect_ratio": "9:16",
                      "resolution": "720p", "style": {AESTHETIC/MEDIUM/AUDIO/NEGATIVE}},
      "assets": {
        "char_venus_s1_turnaround": {"path": "素材库/01_characters/venus/…png",
                                      "kind": "image", "prompt_anchor": "…",
                                      "asset_id": "<平台 asset_id 或 null>",
                                      "audit_status": "active|null"}
      },
      "shots": [{"shot_id": "S01", "duration": 4,
                  "refs": ["char_venus_s1_turnaround", "scene_forge_interior"],
                  "shot_function": "…", "role_binding": "…",
                  "dialogue": [...], "prompt": "…"}]
    }
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from drama.compiler.prompt_compiler import compile_role_binding
from drama.lexicon import CHARACTER_ALIASES
from drama.manifest.assets_manifest import (
    index_by_id as manifest_index,
    load_manifest,
    resolve_entry_path,
    style_constants,
)
from drama.manifest.voice_manifest import load_voice_manifest, voice_entry_by_group
from drama.parser.shots_parser import parse_episode

SLOT_ORDER = ("角色", "场景", "道具", "音色")


def spec_path(project_root: Path, episode: str) -> Path:
    return Path(project_root) / "tools" / "episode_specs" / f"{episode}.json"


def load_episode_spec(project_root: Path, episode: str) -> dict | None:
    path = spec_path(project_root, episode)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"episode_spec 不是合法 JSON：{path}（{exc}）")


def write_episode_spec(project_root: Path, episode: str, spec: dict, *,
                       force: bool = False) -> Path:
    """写分集规格；目标已存在且未指定 force 时抛 SystemExit。"""
    path = spec_path(project_root, episode)
    if path.exists() and not force:
        raise SystemExit(f"规格已存在（用 --force 覆盖）：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def load_registry(project_root: Path) -> dict[str, str]:
    """合并平台 asset_id 注册表：素材生成报告 > 主资产索引 > asset_registry。"""
    registry: dict[str, str] = {}
    root = Path(project_root)
    index = root / "素材库" / "05_index" / "primary_asset_ids.json"
    if index.is_file():
        try:
            registry.update(json.loads(index.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    report = root / "素材库" / "05_index" / "generation_report.json"
    if report.is_file():
        try:
            for item in json.loads(report.read_text(encoding="utf-8")).get("results", []):
                if isinstance(item, dict) and item.get("primary_asset_id"):
                    registry[item["id"]] = item["primary_asset_id"]
        except json.JSONDecodeError:
            pass
    platform_registry = root / "tools" / "asset_registry.json"
    if platform_registry.is_file():
        try:
            for asset_id, entry in json.loads(
                    platform_registry.read_text(encoding="utf-8")).get("assets", {}).items():
                platform_id = (entry or {}).get("platform_asset_id")
                if platform_id:
                    registry[asset_id] = platform_id
        except json.JSONDecodeError:
            pass
    return registry


def _character_anchor_index(shots: dict) -> dict[str, str]:
    """角色标识（venus）→ 英文外观锚点（从各镜 cast 行提取，首个非空者生效）。"""
    anchors: dict[str, str] = {}
    for shot in shots.values():
        for member in shot.get("cast", []):
            anchor = (member.get("anchor") or "").strip()
            if not anchor:
                continue
            name_lower = (member.get("name_en") or "").lower()
            for key, aliases in CHARACTER_ALIASES.items():
                if any(alias in name_lower for alias in aliases) and key not in anchors:
                    anchors[key] = anchor
    return anchors


def _resolve_asset_entry(asset_id: str, project_root: Path,
                         m_index: dict[str, dict], registry: dict[str, str],
                         voice_index: dict[str, dict],
                         char_anchors: dict[str, str]) -> tuple[dict, str | None]:
    """解析单个资产引用 → (entry, warning)。warning 非 None 表示无法完全落位。"""
    root = Path(project_root)
    platform_id = registry.get(asset_id)

    # 1) manifest 登记：以清单为准（路径 / 提示词锚点 / seed 等）
    entry = m_index.get(asset_id)
    if entry:
        path = resolve_entry_path(entry, root)
        anchor = entry.get("prompt", "")
        group = str(entry.get("group", ""))
        if group in char_anchors and entry.get("category") == "01_characters":
            # 角色资产：锚点用分镜里的人物英文锚点（与镜头提示词逐字一致）
            anchor = char_anchors[group]
        return ({
            "path": str(path.relative_to(root)) if path else entry.get("filename"),
            "kind": "image",
            "prompt_anchor": anchor,
            "asset_id": platform_id,
            "audit_status": "active" if platform_id else None,
        }, None if path else f"{asset_id}：manifest 已登记但素材文件无法定位"
                             f"（category={entry.get('category')}）")

    # 2) 音色引用：voice_{group} → 01_characters/{group}/ 下的音色锚点 wav
    if asset_id.startswith("voice_"):
        group = asset_id[len("voice_"):]
        voice = voice_index.get(group)
        candidates = [root / "素材库" / "01_characters" / group /
                      (voice["filename"] if voice else "")]
        if not voice or not candidates[0].is_file():
            anchor_dir = root / "素材库" / "01_characters" / group
            found = sorted(anchor_dir.glob("*anchor-voice.wav")) if anchor_dir.is_dir() else []
            if found:
                candidates = found[:1]
        path = candidates[0] if candidates[0].is_file() else None
        return ({
            "path": str(path.relative_to(root)) if path else None,
            "kind": "audio",
            "prompt_anchor": "",
            "asset_id": platform_id,
            "audit_status": "audio-skip-audit" if path else None,
        }, None if path else f"{asset_id}：找不到音色锚点文件"
                             f"（素材库/01_characters/{group}/*anchor-voice.wav）")

    # 3) 未登记：路径未知，交给人工 / 上游补齐
    return ({
        "path": None,
        "kind": None,
        "prompt_anchor": "",
        "asset_id": platform_id,
        "audit_status": None,
    }, f"{asset_id}：未在 assets_manifest 登记，且不是 voice_* 音色引用")


def build_episode_spec(project_root: Path, episode: str, *,
                       compiled_prompts: dict[str, str] | None = None) -> tuple[dict, list[str]]:
    """从分镜脚本 + manifest + 注册表构建分集执行规格。

    compiled_prompts：drama.compiler.compile_prompt 的 {shot_id: prompt}；
    未提供的镜头 prompt 置空串（由 `opendreamina drama spec` 先编译再组装，
    或人工/智能体作者化填充——对齐奥林匹斯「英文镜头规格作者化提供」的做法）。
    返回 (spec, warnings)。
    """
    root = Path(project_root)
    parsed = parse_episode(episode, root)
    m_index = manifest_index(load_manifest(root))
    registry = load_registry(root)
    voice_index = voice_entry_by_group(load_voice_manifest(root))
    char_anchors = _character_anchor_index(parsed["shots"])

    assets: dict[str, dict] = {}
    warnings: list[str] = []
    header_name = re.sub(r"^#\s*", "", parsed.get("header", "")).strip()

    shots_out: list[dict] = []
    for shot_id, shot in parsed["shots"].items():
        refs: list[str] = []
        for slot in SLOT_ORDER:
            for asset_id in shot.get("assets", {}).get(slot, []):
                if asset_id not in assets:
                    entry, warning = _resolve_asset_entry(
                        asset_id, root, m_index, registry, voice_index, char_anchors)
                    assets[asset_id] = entry
                    if warning:
                        warnings.append(warning)
                if asset_id not in refs:
                    refs.append(asset_id)
        shots_out.append({
            "shot_id": shot_id,
            "duration": shot.get("duration"),
            "refs": refs,
            "shot_function": shot.get("function_zh", ""),
            "role_binding": compile_role_binding(shot),
            "dialogue": shot.get("dialogue", []),
            "prompt": (compiled_prompts or {}).get(shot_id, ""),
        })

    manifest = load_manifest(root)
    defaults = (manifest or {}).get("defaults") or {}
    spec = {
        "episode": episode,
        "episode_name_zh": header_name,
        "source_shotlist": f"分镜脚本/{episode}/shots.md",
        "duration_target_s": sum(s.get("duration") or 0 for s in shots_out),
        "generation": {
            "provider": (manifest or {}).get("provider", ""),
            "model": (manifest or {}).get("model", ""),
            "aspect_ratio": defaults.get("aspect_ratio", "9:16"),
            "resolution": defaults.get("resolution", "720p"),
            "style": style_constants(manifest),
        },
        "assets": assets,
        "shots": shots_out,
    }
    return spec, warnings


def validate_episode_spec(spec: dict) -> list[str]:
    """校验分集规格可执行性：每镜有 prompt、refs 都能落到 assets、有参考的镜能拿到路径。"""
    errors: list[str] = []
    episode = spec.get("episode", "?")
    assets = spec.get("assets") or {}
    for shot in spec.get("shots", []):
        shot_id = shot.get("shot_id", "?")
        if not (shot.get("prompt") or "").strip():
            errors.append(f"{episode}-{shot_id}：prompt 为空（编译或作者化后回填）")
        for ref in shot.get("refs", []):
            if ref not in assets:
                errors.append(f"{episode}-{shot_id}：refs 引用了未登记资产 {ref}")
        image_refs = [r for r in shot.get("refs", []) if (assets.get(r) or {}).get("kind") == "image"]
        if image_refs and any(not (assets[r] or {}).get("path") for r in image_refs):
            errors.append(f"{episode}-{shot_id}：图片参考缺少本地路径，无法上传平台")
    return errors
