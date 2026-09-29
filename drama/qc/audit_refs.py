"""资产引用完整性：扫描分镜脚本引用的资产 ID，并与平台 asset_id 注册表比对。

从《代号奥林匹斯》collect_asset_refs.py 提取。用途：在批量生成前确认
「每条提示词引用的素材都能落到平台 asset_id」，避免出现无参考生成（一致性风险）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from drama.manifest.episode_spec import load_registry
from drama.paths import asset_index_dir, shots_md_path, tools_dir

ASSET_ID_RE = re.compile(r"\b(?:char|scene|prop|crowd|icon|voice)_[a-z0-9_]+\b")


def scan_episode_refs(project_root: Path, episode: str) -> dict[str, set[str]]:
    """返回 {镜号: {资产ID}}，统计「资产绑定」行与总览表行中出现的资产 ID。"""
    path = shots_md_path(project_root, episode)
    if not path.is_file():
        raise SystemExit(f"分镜文件不存在：{path}")
    per_shot: dict[str, set[str]] = {}
    current = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^##\s+(EP\d+-S\d+)\s*$", line)
        if heading:
            current = heading.group(1)
            per_shot.setdefault(current, set())
            continue
        if line.startswith("**资产绑定："):
            per_shot.setdefault(current, set()).update(ASSET_ID_RE.findall(line))
        elif line.startswith("| EP") and "|" in line:
            cell = line.split("|")[1].strip()
            if re.match(r"^EP\d+-S\d+$", cell):
                per_shot.setdefault(cell, set()).update(ASSET_ID_RE.findall(line))
    return per_shot


def audit_episode_refs(project_root: Path, episodes: list[str]) -> dict:
    """多集引用审计：每集引用的资产 → 是否有平台 asset_id / 本地文件是否存在。"""
    from drama.manifest.assets_manifest import index_by_id, load_manifest, resolve_entry_path

    root = Path(project_root)
    registry = load_registry(root)
    m_index = index_by_id(load_manifest(root))
    index_dir = asset_index_dir(root)

    episodes_out: list[dict] = []
    for episode in episodes:
        per_shot = scan_episode_refs(root, episode)
        used = sorted({a for refs in per_shot.values() for a in refs})
        assets_out: list[dict] = []
        for asset_id in used:
            entry = m_index.get(asset_id)
            if entry:
                path = resolve_entry_path(entry, root)
                file_exists = bool(path and path.is_file())
                display_path = str(path.relative_to(root)) if path else entry.get("filename")
            elif asset_id.startswith("voice_"):
                # 音色引用不在 assets_manifest：按 voice_{group} 约定检查音色锚点文件
                group = asset_id[len("voice_"):]
                candidates = sorted((root / "素材库" / "01_characters" / group)
                                    .glob("*anchor-voice.wav"))
                file_exists = bool(candidates)
                display_path = (str(candidates[0].relative_to(root))
                                if candidates else f"素材库/01_characters/{group}/*anchor-voice.wav")
                path = candidates[0] if candidates else None
            else:
                path = None
                file_exists = False
                display_path = None
            assets_out.append({
                "id": asset_id,
                "in_manifest": entry is not None,
                "path": display_path,
                "file_exists": file_exists,
                "platform_asset_id": registry.get(asset_id),
            })
        missing_registry = [a["id"] for a in assets_out if not a["platform_asset_id"]]
        missing_files = [a["id"] for a in assets_out if not a["file_exists"]]
        episodes_out.append({
            "episode": episode,
            "shots": len(per_shot),
            "referenced_assets": len(used),
            "assets": assets_out,
            "missing_platform_id": missing_registry,
            "missing_files": missing_files,
            "shots_by_asset": {asset: sorted(s for s, refs in per_shot.items() if asset in refs)
                               for asset in used},
        })
    return {
        "project": str(root),
        "registry_size": len(registry),
        "registry_sources": [
            "素材库/05_index/primary_asset_ids.json",
            "素材库/05_index/generation_report.json",
            str(tools_dir(root).relative_to(root) / "asset_registry.json")
            if tools_dir(root).is_dir() else "tools/asset_registry.json",
        ],
        "index_dir_exists": index_dir.is_dir(),
        "episodes": episodes_out,
    }
