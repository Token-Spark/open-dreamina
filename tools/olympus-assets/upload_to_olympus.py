#!/usr/bin/env python3
"""批量上传短剧素材到 Open Dreamina 素材库，打 Olympus 标签并同步云端。

针对「短剧剧本代号奥林匹斯/素材库」目录结构设计：
    01_characters/<group>/<GROUP>_PRIMARY_anchor-portrait.png (+ _anchor-voice.wav)
    01_characters/<group>/<GROUP>_<variant>_{halfbody,turnaround}.png
    02_scenes/<group>/<SCENE>_{PRIMARY_wide,interior,exterior,...}.png
    03_props/props/PROP_<name>.png
    04_iconic_scenes/iconic/EP<nn>_<slug>.png
    05_index/{generation_report,primary_asset_ids,voice_generation_report}.json

规则：
- 跳过 `_pilot_style/`（画风试片）与任何 `_superseded_*/`（废弃版本）目录。
- 每个 `*PRIMARY_anchor-portrait.png` 与其同名 `*PRIMARY_anchor-voice.wav` 合并为
  一条素材（图片+音色），名称取自索引报告的中文名。
- 其余图片各自成为一条素材（素材库模型仅支持单图+单音）。
- 标签：`[<项目标签>, <分类>, <分组>]`，如 ["Olympus", "character", "apollo"]。

用法：
    python upload_to_olympus.py --source "<素材库绝对路径>" --dry-run
    python upload_to_olympus.py --source "<素材库绝对路径>"
    python upload_to_olympus.py --source "<素材库绝对路径>" --skip-sync
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = os.environ.get("OPEN_DREAMINA_API_BASE", "http://localhost:10130/api/v1")
TIMEOUT = int(os.environ.get("OPEN_DREAMINA_API_TIMEOUT", "180"))

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}

# 顶层目录 → 素材库分类
CATEGORY_BY_TOP_DIR = {
    "01_characters": "character",
    "02_scenes": "scene",
    "03_props": "prop",
    "04_iconic_scenes": "keyframe",
}

_PRIMARY_ANCHOR_RE = re.compile(r"^(?P<prefix>.+?)_PRIMARY_anchor-(?P<kind>portrait|voice)$")


# ---------------- HTTP ----------------

def _api_json(method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    """发送 JSON 请求并解析响应。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(f"{API_BASE}{path}", data=data, method=method,
                  headers={"Content-Type": "application/json"})
    return _send(req)


def _api_upload(file_path: Path) -> dict[str, Any]:
    """以 multipart/form-data 上传文件到 /assets/upload。"""
    boundary = "----Olympus" + os.urandom(12).hex()
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    body = head + file_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = Request(f"{API_BASE}/assets/upload", data=body, method="POST",
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return _send(req)


def _send(req: Request) -> dict[str, Any]:
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace") if e.fp else ""
        raise RuntimeError(f"HTTP {e.code} {req.full_url}: {detail[:300]}") from e
    except URLError as e:
        raise RuntimeError(f"网络错误 {req.full_url}: {e}") from e


# ---------------- 索引元数据 ----------------

def load_index(index_dir: Path) -> dict[str, dict]:
    """读取 generation_report.json，建立「绝对路径小写 → 元数据」映射。"""
    report = index_dir / "generation_report.json"
    if not report.exists():
        return {}
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    index: dict[str, dict] = {}
    for item in data.get("results", []):
        file_path = item.get("file")
        if file_path:
            index[str(Path(file_path)).lower()] = item
    voice_report = index_dir / "voice_generation_report.json"
    if voice_report.exists():
        try:
            vdata = json.loads(voice_report.read_text(encoding="utf-8"))
            for item in vdata.get("results", []):
                fp = item.get("file")
                if fp:
                    index.setdefault(str(Path(fp)).lower(), {})["_voice"] = item
        except (OSError, ValueError):
            pass
    return index


def _display_name(file_path: Path, index: dict[str, dict]) -> str:
    """素材展示名：优先索引中的中文名，缺失时由文件名推导。"""
    meta = index.get(str(file_path).lower(), {})
    name_zh = (meta.get("name_zh") or "").strip()
    if name_zh:
        return name_zh[:100]
    stem = file_path.stem.replace("_", " ").replace("-", " ").strip()
    return (stem or file_path.name)[:100]


# ---------------- 上传计划 ----------------

def _is_skipped_dir(path: Path, source_root: Path) -> bool:
    """跳过试片目录与非正式版本目录。"""
    try:
        parts = path.relative_to(source_root).parts
    except ValueError:
        return True
    return any(p.startswith("_pilot") or "_superseded" in p for p in parts)


def build_plan(source_root: Path, index: dict[str, dict]) -> list[dict]:
    """扫描素材库，产出待上传单元列表。

    每个单元：{image, audio, name, category, group, rel_path}
    """
    units: list[dict] = []
    for top_dir, category in CATEGORY_BY_TOP_DIR.items():
        base = source_root / top_dir
        if not base.is_dir():
            continue
        for sub_dir in sorted(p for p in base.rglob("*") if p.is_dir()):
            if _is_skipped_dir(sub_dir, source_root):
                continue
            images: list[Path] = []
            voices: dict[str, Path] = {}
            for f in sorted(sub_dir.iterdir()):
                if not f.is_file() or _is_skipped_dir(f, source_root):
                    continue
                ext = f.suffix.lower()
                if ext in IMAGE_EXTS:
                    images.append(f)
                elif ext in AUDIO_EXTS:
                    m = _PRIMARY_ANCHOR_RE.match(f.stem)
                    if m and m.group("kind") == "voice":
                        voices[m.group("prefix")] = f
            if not images and not voices:
                continue
            group = sub_dir.name
            consumed: set[str] = set()
            for img in images:
                audio: Path | None = None
                m = _PRIMARY_ANCHOR_RE.match(img.stem)
                if m and m.group("kind") == "portrait":
                    audio = voices.get(m.group("prefix"))
                    if audio:
                        consumed.add(m.group("prefix"))
                units.append({
                    "image": img,
                    "audio": audio,
                    "name": _display_name(img, index),
                    "category": category,
                    "group": group,
                    "rel_path": img.relative_to(source_root).as_posix(),
                })
            for prefix, voice in voices.items():
                if prefix in consumed:
                    continue
                units.append({
                    "image": None, "audio": voice,
                    "name": _display_name(voice, index),
                    "category": category, "group": group,
                    "rel_path": voice.relative_to(source_root).as_posix(),
                })
    return units


# ---------------- 执行 ----------------

def _existing_names(tag: str) -> set[str]:
    """已存在的素材名（用于幂等跳过）。"""
    try:
        data = _api_json("GET", f"/creation-assets?tags={tag}&page_size=200")
    except RuntimeError:
        return set()
    return {item.get("name", "") for item in data.get("items", [])}


def upload_unit(unit: dict, tag: str) -> dict:
    """上传一个单元：媒体 → 素材条目。返回结果摘要。"""
    image_id = audio_id = None
    if unit["image"]:
        image_id = _api_upload(unit["image"])["id"]
    if unit["audio"]:
        audio_id = _api_upload(unit["audio"])["id"]

    payload: dict[str, Any] = {
        "name": unit["name"],
        "category": unit["category"],
        "description": f"来源：{unit['rel_path']}",
        "tags": [tag, unit["category"], unit["group"]],
    }
    if image_id:
        payload["image_asset_id"] = image_id
    if audio_id:
        payload["audio_asset_id"] = audio_id

    resp = _api_json("POST", "/creation-assets", payload)
    sync = resp.get("sync_result") or {}
    return {"ca_id": resp.get("id", ""), "sync": sync.get("status", "")}


def main() -> int:
    parser = argparse.ArgumentParser(description="上传短剧素材到 Open Dreamina 素材库（Olympus 标签）")
    parser.add_argument("--source", required=True, help="素材库根目录（含 01_characters 等子目录）")
    parser.add_argument("--tag", default="Olympus", help="项目标签（默认 Olympus）")
    parser.add_argument("--dry-run", action="store_true", help="只输出上传计划")
    parser.add_argument("--skip-sync", action="store_true", help="跳过末尾的云端同步")
    parser.add_argument("--limit", type=int, default=0, help="仅上传前 N 个单元（调试用）")
    args = parser.parse_args()

    source_root = Path(args.source).expanduser().resolve()
    if not source_root.is_dir():
        print(f"[ERROR] 目录不存在：{source_root}", file=sys.stderr)
        return 1

    index = load_index(source_root / "05_index")
    units = build_plan(source_root, index)
    if args.limit:
        units = units[: args.limit]

    with_audio = sum(1 for u in units if u["audio"])
    print(f"[计划] 素材单元 {len(units)} 条（含音色 {with_audio} 条），标签「{args.tag}」")
    by_category: dict[str, int] = {}
    for u in units:
        by_category[u["category"]] = by_category.get(u["category"], 0) + 1
    for cat, count in sorted(by_category.items()):
        print(f"        {cat:<10} {count} 条")

    if args.dry_run:
        print("\n[DRY-RUN] 明细：")
        for i, u in enumerate(units, 1):
            media = "image+audio" if u["audio"] else ("image" if u["image"] else "audio")
            print(f"  {i:>3}. [{u['category']:<9}] {u['group']:<14} {media:<11} {u['name']}")
        return 0

    existing = _existing_names(args.tag)
    if existing:
        print(f"[幂等] 云端已有 {len(existing)} 条同名素材，将跳过")

    results: list[dict] = []
    ok = skipped = failed = 0
    started = time.time()
    for i, unit in enumerate(units, 1):
        if unit["name"] in existing:
            skipped += 1
            print(f"  [{i}/{len(units)}] SKIP  {unit['name']}（已存在）")
            results.append({
                "name": unit["name"], "category": unit["category"],
                "group": unit["group"], "rel_path": unit["rel_path"],
                "has_audio": bool(unit["audio"]), "status": "skipped",
            })
            continue
        print(f"  [{i}/{len(units)}] 上传 {unit['name']} ...", end=" ", flush=True)
        try:
            info = upload_unit(unit, args.tag)
            ok += 1
            print(f"OK (ca={info['ca_id'][:8]}, sync={info['sync'] or '-'})")
            results.append({
                "name": unit["name"], "category": unit["category"],
                "group": unit["group"], "rel_path": unit["rel_path"],
                "has_audio": bool(unit["audio"]), "status": "ok", **info,
            })
        except Exception as e:  # noqa: BLE001 单条失败不阻断批量
            failed += 1
            print(f"FAILED: {e}")
            results.append({"name": unit["name"], "rel_path": unit["rel_path"],
                            "status": "failed", "error": str(e)})

    elapsed = time.time() - started
    print(f"\n[完成] 成功 {ok}，跳过 {skipped}，失败 {failed}，耗时 {elapsed:.0f}s")

    if not args.skip_sync and ok > 0:
        print(f"[同步] 推送标签「{args.tag}」到云端 ...")
        try:
            result = _api_json("POST", "/creation-assets/sync", {"tag": args.tag})
            stats: dict[str, int] = {}
            for item in result.get("items", []):
                stats[item.get("status", "?")] = stats.get(item.get("status", "?"), 0) + 1
            print(f"        {stats}")
        except Exception as e:  # noqa: BLE001
            print(f"        [同步失败] {e}\n        可稍后重试：POST /api/v1/creation-assets/sync")

    report_path = Path(__file__).resolve().parent / "olympus_upload_report.json"
    report_path.write_text(
        json.dumps({"tag": args.tag, "source": str(source_root), "total": len(units),
                    "ok": ok, "skipped": skipped, "failed": failed,
                    "elapsed_s": round(elapsed, 1), "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[报告] {report_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
