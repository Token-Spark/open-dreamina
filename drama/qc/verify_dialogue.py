"""台词同步校验：核对 shots.md 台词块的解析完整性与「台词量 vs 镜头时长」。"""

from __future__ import annotations

import re
from pathlib import Path

from drama.paths import shots_md_path
from drama.parser.shots_parser import parse_episode

# 每秒可念的英文词数（无语速标注时的兜底值；短剧台词通常 2~3 词/秒）
DEFAULT_WORDS_PER_SECOND = 2.5
DIALOGUE_LINE_RE = re.compile(r"台词[：:]")


def _estimate_speech_seconds(text: str, rate: float | None) -> float:
    """按词数 / 语速估算台词秒数；语速缺省用兜底值。"""
    words = len(re.findall(r"[A-Za-z']+", text))
    words_per_second = rate if rate and rate > 0 else DEFAULT_WORDS_PER_SECOND
    return words / words_per_second


def check_episode_dialogue(project_root: Path, episode: str, *,
                           parsed: dict | None = None) -> dict:
    """整集台词校验，返回逐镜明细与问题清单。

    检查项：
      1. 台词行解析完整性：shots.md 中「台词：」行数 ≠ 解析出的台词数 → 说明
         引号格式不符（如缺引号 / 中英文引号混用），解析器静默丢行
      2. 台词量与时长匹配：估算念白秒数 > 镜头时长 → 模型大概率念不完
      3. 覆盖统计：有台词镜数 / 画外音镜数
    """
    root = Path(project_root)
    if parsed is None:
        parsed = parse_episode(episode, root)

    # 逐镜统计原始「台词：」行数（含解析失败的），与解析结果比对；
    # 与解析器一致地跳过 HTML 注释块，避免模板/机器缓存内容干扰计数
    from drama.parser.shots_parser import strip_html_comments

    raw_lines: dict[str, int] = {}
    current = ""
    for line in strip_html_comments(
            shots_md_path(root, episode).read_text(encoding="utf-8").splitlines()):
        heading = re.match(r"^##\s+(EP\d+-S\d+)\s*$", line)
        if heading:
            current = heading.group(1)
            raw_lines.setdefault(current, 0)
            continue
        if current and DIALOGUE_LINE_RE.search(line) and not line.startswith("**"):
            raw_lines[current] = raw_lines.get(current, 0) + 1

    shots_out: list[dict] = []
    issues: list[str] = []
    for shot_id, shot in parsed["shots"].items():
        dialogue = shot.get("dialogue", [])
        estimated = sum(_estimate_speech_seconds(l["text"], l.get("rate")) for l in dialogue)
        duration = shot.get("duration") or 0
        entry = {
            "shot_id": shot_id,
            "dialogue_lines": len(dialogue),
            "raw_dialogue_lines": raw_lines.get(shot_id, 0),
            "estimated_speech_s": round(estimated, 1),
            "duration_s": duration,
            "vo_lines": sum(1 for l in dialogue if l.get("form") == "vo"),
        }
        if entry["raw_dialogue_lines"] != len(dialogue):
            entry["unparsed"] = entry["raw_dialogue_lines"] - len(dialogue)
            issues.append(
                f"{shot_id}：{entry['unparsed']} 条台词未解析"
                "（检查引号格式：台词需写在英文/中文引号内，如 台词：\"...\"）")
        if duration and estimated > duration + 0.5:
            issues.append(
                f"{shot_id}：台词量约 {estimated:.1f}s 超出镜头时长 {duration}s，模型念不完")
        shots_out.append(entry)

    with_dialogue = sum(1 for s in shots_out if s["dialogue_lines"])
    return {
        "episode": episode,
        "shots": shots_out,
        "issues": issues,
        "stats": {
            "total_shots": len(shots_out),
            "shots_with_dialogue": with_dialogue,
            "shots_with_vo": sum(1 for s in shots_out if s["vo_lines"]),
            "estimated_total_speech_s": round(sum(s["estimated_speech_s"] for s in shots_out), 1),
        },
    }
