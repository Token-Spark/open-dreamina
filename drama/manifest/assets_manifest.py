"""资产清单（tools/assets_manifest.json）的加载、校验与路径解析。

manifest 是全部素材资产的权威清单：每项资产记录生成方式（text2img / img2img）、
seed、文件名与完整生成提示词；全局风格常量（style）与一致性策略也在此声明。

schema（对齐《代号奥林匹斯》实测数据）：

    {
      "version": 1,
      "project": "项目名",
      "provider": "sparkhub-seedream",
      "model": "doubao_seedream_5_pro",
      "style": {"aesthetic": "...", "medium": "...", "audio": "...", "negative": "..."},
      "defaults": {"aspect_ratio": "9:16", "resolution": "2K", "poll": 600},
      "consistency_strategy": {...},          # 可选，四层锚点说明
      "assets": [
        {"id": "char_venus_primary", "category": "01_characters", "group": "venus",
         "name_zh": "...", "mode": "text2img|img2img", "is_primary": true, "seed": 10001,
         "filename": "VENUS_PRIMARY_anchor-portrait.png", "prompt": "...",
         "reference_primary": "...", "strength": 0.5}   # img2img 专属
      ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FIELDS = ("id", "category", "group", "mode", "filename")
KNOWN_CATEGORIES = ("01_characters", "02_scenes", "03_props", "04_iconic_scenes", "_pilot_style")
# 一致性锚点（组内 is_primary 唯一）只对人物 / 场景生效；
# 道具、名场面、风格试验（_pilot_style）组内可有多个 primary。
ANCHOR_CATEGORIES = ("01_characters", "02_scenes")
CATEGORY_DIRS = {
    # category → 素材库下的物理目录；group 为子目录（props 例外：统一在 props/ 下）
    "01_characters": "01_characters/{group}",
    "02_scenes": "02_scenes/{group}",
    "03_props": "03_props/props",
    "04_iconic_scenes": "04_iconic_scenes",
    "_pilot_style": "_pilot_style",
}


def manifest_path(project_root: Path) -> Path:
    return Path(project_root) / "tools" / "assets_manifest.json"


def load_manifest(project_root: Path) -> dict | None:
    """加载 manifest；文件不存在返回 None（项目尚无素材时是合法状态）。"""
    path = manifest_path(project_root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"assets_manifest.json 不是合法 JSON：{path}（{exc}）")


def index_by_id(manifest: dict | None) -> dict[str, dict]:
    """资产 id → 条目。重复 id 以后者为准（validate_manifest 会报错）。"""
    index: dict[str, dict] = {}
    for entry in (manifest or {}).get("assets", []):
        if isinstance(entry, dict) and entry.get("id"):
            index[entry["id"]] = entry
    return index


def validate_manifest(manifest: dict | None) -> dict:
    """校验 manifest 完整性与一致性。

    返回 {"errors": [...], "warnings": [...]}；errors 非空视为不可用，
    warnings 是数据演化出的合法形态（如角色多套锚点肖像）但值得知情。
    """
    if manifest is None:
        return {"errors": ["assets_manifest.json 不存在（tools/assets_manifest.json）"],
                "warnings": []}
    errors: list[str] = []
    warnings: list[str] = []
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        # 新项目尚未开始素材生产是合法状态，引导而非报错
        return {"errors": [], "warnings": ["assets 为空：素材生产后逐条登记到 manifest"
                                           "（生成前可用 `drama assets` 核对引用落位）"]}
    seen: dict[str, int] = {}
    primaries: set[str] = set()
    multi_primary_keys: set[str] = set()
    for position, entry in enumerate(assets):
        if not isinstance(entry, dict):
            errors.append(f"assets[{position}] 不是对象")
            continue
        asset_id = entry.get("id")
        if not asset_id:
            errors.append(f"assets[{position}] 缺少 id")
            continue
        if asset_id in seen:
            errors.append(f"资产 id 重复：{asset_id}（第 {seen[asset_id]} 与 {position} 项）")
        seen[asset_id] = position
        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                errors.append(f"{asset_id} 缺少必填字段 {field}")
        if entry.get("category") not in KNOWN_CATEGORIES:
            errors.append(f"{asset_id} category 非法：{entry.get('category')!r}"
                          f"（应为 {'/'.join(KNOWN_CATEGORIES)}）")
        if entry.get("mode") not in ("text2img", "img2img"):
            errors.append(f"{asset_id} mode 非法：{entry.get('mode')!r}")
        if entry.get("mode") == "text2img" and not entry.get("prompt"):
            errors.append(f"{asset_id} 为 text2img 但缺少 prompt")
        # img2img 的参考锚点有四种写法（对齐实测数据）：
        # reference_primary / reference_primaries / self_reference / use_style_reference；
        # prompt 可继承顶层 prompt_templates（如三视图模板）。
        if entry.get("mode") == "img2img" and not any(
                entry.get(key) for key in ("reference_primary", "reference_primaries",
                                           "self_reference", "use_style_reference")):
            errors.append(f"{asset_id} 为 img2img 但缺少任何参考锚点字段"
                          "（reference_primary(s) / self_reference / use_style_reference）")
        if entry.get("is_primary") and entry.get("category") in ANCHOR_CATEGORIES:
            key = f"{entry.get('category')}:{entry.get('group')}"
            if key in primaries and key not in multi_primary_keys:
                multi_primary_keys.add(key)
                warnings.append(f"{key} 组内存在多个 is_primary 锚点"
                                "（角色多时期/场景多变体时属正常，请确认每个都有固定 seed）")
            primaries.add(key)
            if entry.get("seed") is None:
                warnings.append(f"{asset_id} 为 primary 但未固定 seed（复现性下降）")
    return {"errors": errors, "warnings": warnings}


def resolve_entry_path(entry: dict, project_root: Path) -> Path | None:
    """资产条目 → 素材库物理路径（不存在对应目录约定时返回 None）。"""
    template = CATEGORY_DIRS.get(entry.get("category", ""))
    if not template or not entry.get("filename"):
        return None
    return (Path(project_root) / "素材库" / template.format(group=entry.get("group", ""))
            / entry["filename"])


def style_constants(manifest: dict | None) -> dict[str, str]:
    """提取全局风格常量：AESTHETIC / MEDIUM / AUDIO / NEGATIVE。

    来源优先级：manifest.style 字段（aesthetic/medium/audio/negative）。
    """
    style = (manifest or {}).get("style") or {}
    return {
        "AESTHETIC": str(style.get("aesthetic", "") or ""),
        "MEDIUM": str(style.get("medium", "") or ""),
        "AUDIO": str(style.get("audio", "") or ""),
        "NEGATIVE": str(style.get("negative", "") or ""),
    }
