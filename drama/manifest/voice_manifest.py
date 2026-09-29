"""音色清单（tools/voice_manifest.json）的加载与校验。

schema（对齐《代号奥林匹斯》实测数据）：

    {
      "version": 1,
      "project": "项目名",
      "provider": "...",
      "voices": [
        {"group": "venus",                 # 角色标识（对应 01_characters/{group}/）
         "character_zh": "维纳斯", "character_en": "Venus",
         "filename": "VENUS_PRIMARY_anchor-voice.wav",
         "voice_type": "en_female_...",    # TTS 音色 id
         "voice_name": "Elaine",
         "casting_reason": "...",          # 选角理由（可选）
         "languages": ["en", ...]}         # 可选；英语剧要求含 en
      ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FIELDS = ("group", "filename", "voice_type", "voice_name")


def voice_manifest_path(project_root: Path) -> Path:
    return Path(project_root) / "tools" / "voice_manifest.json"


def load_voice_manifest(project_root: Path) -> dict | None:
    path = voice_manifest_path(project_root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"voice_manifest.json 不是合法 JSON：{path}（{exc}）")


def validate_voice_manifest(manifest: dict | None, *, expected_language: str = "en") -> list[str]:
    """校验音色清单；expected_language 为剧集对白语言（英语剧默认 en）。"""
    if manifest is None:
        return []
    errors: list[str] = []
    voices = manifest.get("voices")
    if not isinstance(voices, list):
        return ["voices 缺失或不是数组"]
    seen: set[str] = set()
    for position, item in enumerate(voices):
        if not isinstance(item, dict):
            errors.append(f"voices[{position}] 不是对象")
            continue
        group = item.get("group")
        if not group:
            errors.append(f"voices[{position}] 缺少 group")
            continue
        if group in seen:
            errors.append(f"音色 group 重复：{group}（每个角色固定一个音色锚点）")
        seen.add(group)
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                errors.append(f"音色 {group} 缺少必填字段 {field}")
        languages = item.get("languages") or []
        if languages and expected_language not in languages:
            errors.append(f"音色 {group} 不支持对白语言 {expected_language}（languages={languages}）")
    return errors


def voice_entry_by_group(manifest: dict | None) -> dict[str, dict]:
    """group → 音色条目。"""
    return {item["group"]: item
            for item in (manifest or {}).get("voices", [])
            if isinstance(item, dict) and item.get("group")}
