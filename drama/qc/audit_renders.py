"""成片技术验收（逐镜核对文件唯一性、画幅、时长、音轨）。

从《代号奥林匹斯》audit_episode_renders.py 提取：去掉对 epXX_shots_data /
episode_config 的耦合，镜头清单改读分镜脚本解析结果，输出根按标准目录约定。

验收项（对应分镜脚本制作规范硬性规格与音频约定）：
  1. 每镜至少一份成片；多份时提示交付前确认保留版本
  2. 画幅：默认竖屏 9:16（容差 2%，可用 --aspect 调整）
  3. 时长：不短于模型下限，不明显超出投递时长
  4. 音轨：必须存在声音（禁止整体静音）；给出平均电平用于人工判断

不负责：判断是否含背景音乐（需人工试听）；依赖 ffprobe / ffmpeg（缺失时
对应检查项降级跳过，不阻断其余验收）。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ASPECT_RATIO_TOLERANCE = 0.02
DURATION_TOLERANCE_S = 1.5
SILENCE_THRESHOLD_DB = -50.0
ADVISORY_VOLUME_DB = -40.0
# 渲染目录约定：video_renders/<镜号>*/ 下的 mp4（跳过 `_` 前缀的废弃版本目录）
RENDER_FILE_RE = re.compile(r"\.mp4$", re.IGNORECASE)


def probe(path: Path) -> dict | None:
    """用 ffprobe 读取容器与流信息；ffprobe 缺失或解析失败返回 None。"""
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None


def mean_volume_db(path: Path) -> tuple[float | None, str | None]:
    """用 ffmpeg volumedetect 估算平均电平（dBFS）。

    返回 (电平, 错误说明)：ffmpeg 缺失或滤镜执行失败时返回 (None, 原因)，
    调用方把该镜的音量检查标记为跳过，不阻断其它验收。
    """
    try:
        completed = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None, "ffmpeg 不可用"
    match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", completed.stderr)
    if not match:
        return None, "volumedetect 无输出"
    return float(match.group(1)), None


def _parse_aspect(text: str) -> float:
    """'9:16' → 0.5625。"""
    try:
        width, height = text.lower().split(":", 1)
        return int(width) / int(height)
    except (ValueError, ZeroDivisionError) as exc:
        raise SystemExit(f"画幅格式不合法：{text!r}（应为 9:16 / 16:9 等）") from exc


def collect_render_files(output_root: Path, shot_id: str) -> list[Path]:
    """收集某镜号的成片文件：video_renders/**/{shot_id}*.mp4，跳过 `_` 前缀目录。

    shot_id 支持 `EP05-S01`（全前缀）与渲染文件常用的短前缀 `S01_` 两种命名；
    多版本文件（同前缀多份）全部返回，由验收项提示确认保留版本。
    """
    if not output_root.is_dir():
        return []
    short_id = shot_id.split("-", 1)[-1] if "-" in shot_id else shot_id
    prefixes = [shot_id, short_id]

    def _matches(name: str) -> bool:
        return any(name == p or name.startswith(p + "_")
                   or name.startswith(p + "-") or name.startswith(p + ".")
                   for p in prefixes)

    files: list[Path] = []
    for candidate in sorted(output_root.rglob("*")):
        if not candidate.is_file() or not RENDER_FILE_RE.search(candidate.name):
            continue
        # `_` 前缀目录（_superseded_* 等）是废弃版本，验收只看当前交付
        if any(part.startswith("_") for part in candidate.relative_to(output_root).parts):
            continue
        if _matches(candidate.stem):
            files.append(candidate)
    return files


def audit_shot(shot: dict, output_root: Path, *, min_duration: int = 4,
               target_aspect: float = 9 / 16) -> dict:
    """验收单镜：文件唯一性 / 画幅 / 时长 / 音轨。"""
    shot_id = shot["shot_id"]
    files = collect_render_files(output_root, shot_id)
    nominal = shot.get("duration") or 0
    expected = max(min_duration, nominal)
    result: dict = {
        "shot_id": shot_id,
        "nominal_duration_s": nominal,
        "expected_render_duration_s": expected,
        "files": [f.name for f in files],
        "issues": [],
        "advisories": [],
    }
    if not files:
        result["issues"].append("缺少成片文件")
        return result
    if len(files) > 1:
        result["issues"].append(f"存在 {len(files)} 份成片，交付前需确认保留哪一份")

    info = probe(files[-1])
    if info is None:
        result["issues"].append("ffprobe 无法解析该文件（或 ffprobe 未安装）")
        return result

    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    audio_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    duration = float(info.get("format", {}).get("duration") or 0)

    result["file"] = files[-1].name
    result["duration_s"] = round(duration, 2)
    result["audio_streams"] = len(audio_streams)

    if video:
        width, height = int(video["width"]), int(video["height"])
        result["resolution"] = f"{width}x{height}"
        if not height or abs((width / height) - target_aspect) / target_aspect > ASPECT_RATIO_TOLERANCE:
            result["issues"].append(
                f"画幅 {width}x{height} 偏离目标画幅超过 {ASPECT_RATIO_TOLERANCE:.0%} 容差")
    else:
        result["issues"].append("没有视频流")

    if duration < min_duration - 0.5:
        result["issues"].append(f"时长 {duration:.1f}s 短于模型下限 {min_duration}s")
    if nominal and duration > expected + DURATION_TOLERANCE_S:
        result["issues"].append(
            f"时长 {duration:.1f}s 明显超出投递时长 {expected}s，剪辑时需裁切")

    if not audio_streams:
        result["issues"].append("无音轨（违反「人声/音效/环境音必须保留」约定）")
    else:
        level, error = mean_volume_db(files[-1])
        if level is None:
            result["advisories"].append(f"平均电平未测得（{error}），需人工试听")
        elif level < SILENCE_THRESHOLD_DB:
            result["issues"].append(f"平均电平 {level}dBFS 近似静音，需人工确认")
        elif level < ADVISORY_VOLUME_DB:
            result["advisories"].append(
                f"平均电平 {level}dBFS 偏低，剪辑时建议提升增益或与相邻镜头对齐")
        else:
            result["mean_volume_db"] = level
    return result


def audit_episode_renders(project_root: Path, episode: str, *,
                          min_duration: int = 4, aspect: str = "9:16",
                          parsed: dict | None = None) -> dict:
    """整集技术验收。parsed 可传入 parse_episode 结果（避免重复解析）。"""
    from drama.parser.shots_parser import parse_episode
    from drama.paths import video_renders_dir

    root = Path(project_root)
    if parsed is None:
        parsed = parse_episode(episode, root)
    output_root = video_renders_dir(root, episode)
    target_aspect = _parse_aspect(aspect)

    import shutil

    reports = [audit_shot(shot, output_root, min_duration=min_duration,
                          target_aspect=target_aspect)
               for shot in parsed["shots"].values()]
    failed = [item for item in reports if item["issues"]]
    levels = [item["mean_volume_db"] for item in reports
              if item.get("mean_volume_db") is not None]
    summary = {
        "episode": episode,
        "ffprobe_available": shutil.which("ffprobe") is not None,
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "total_shots": len(reports),
        "delivered_shots": sum(1 for item in reports if item.get("file")),
        "passed": len(reports) - len(failed),
        "failed": len(failed),
        "failed_shots": [item["shot_id"] for item in failed],
        "volume_advisory_shots": [item["shot_id"] for item in reports if item.get("advisories")],
        "nominal_duration_s": sum(item["nominal_duration_s"] for item in reports),
        "actual_duration_s": round(sum(item.get("duration_s", 0) for item in reports), 2),
        "audio_present_shots": sum(1 for item in reports if item.get("audio_streams")),
        "mean_volume_db_range": [min(levels), max(levels)] if levels else None,
        "manual_qc_pending": ["逐镜试听确认不含模型自带配乐（技术手段无法自动判定）"],
    }
    return {"summary": summary, "shots": reports}
