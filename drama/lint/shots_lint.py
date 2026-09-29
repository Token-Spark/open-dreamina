"""分镜脚本格式规范校验（`opendreamina drama lint` 的实现）。

校验依据：《代号奥林匹斯》_SPEC_分镜模板规范.md 的硬性规则——
  · 单集镜头数 18（±1）、单镜 2-8s、时长总和精确等于目标时长（默认 90s）
  · 总览表 15 列齐全、逐镜块必填行齐全、禁止相对引用（「同上」）
  · 每集至少 1 个 POV 主观镜头
  · 摄影语言 / 表情词应在映射表内（未命中会被编译器丢弃，污染一致性）

errors 违反硬性规则（valid=False）；warnings 是不影响解析但会降低
生成质量或需要人工确认的问题。
"""

from __future__ import annotations

import re
from pathlib import Path

from drama.compiler.prompt_compiler import EXPRESSION_MAP, best_match
from drama.parser.shots_parser import CAMERA_PHRASE, parse_episode, parse_overview
from drama.paths import shots_md_path
from drama.qc.verify_dialogue import check_episode_dialogue

REQUIRED_BLOCK_LINES = (
    ("**资产绑定：", "资产绑定"),
    ("**镜头功能：", "镜头功能"),
    ("**人物：", "人物"),
    ("**场景描述：", "场景描述"),
    ("**台词同步：", "台词同步"),
    ("**音效设计", "音效设计"),
    ("**基础环境音", "基础环境音"),
    ("**动作触发音", "动作触发音"),
    ("**特效音", "特效音"),
)
DASH_SET = {"—", "无", "–", "-", "―", ""}
HEADING_RE = re.compile(r"^##\s+(EP\d+-S\d+)\s*$")
# 总览表表头：同时含「镜号」与「时长」（资产绑定表只含镜号，不会误伤）
OVERVIEW_HEADER_RE = re.compile(r"^\|[^|]*镜号[^|]*时长")
# 总览表数据行：首列即镜号（如 | EP05-S01 | 4 | wide | …）
OVERVIEW_HEADING_ROW_RE = re.compile(r"^\|\s*EP\d+-S\d+\s*\|")


def lint_episode(project_root: Path, episode: str, *, target_duration: int = 90,
                 shot_min: int = 2, shot_max: int = 8, soft_max: int = 6,
                 expected_shots: int = 18) -> dict:
    """整集规范校验。target_duration / 镜头数上下限可按项目要求调整。"""
    root = Path(project_root)
    path = shots_md_path(root, episode)
    errors: list[str] = []
    warnings: list[str] = []

    if not path.is_file():
        return {"episode": episode, "valid": False,
                "errors": [f"分镜文件不存在：{path}"], "warnings": [], "stats": {}}
    from drama.parser.shots_parser import strip_html_comments

    lines = strip_html_comments(path.read_text(encoding="utf-8").splitlines())

    header = next((l for l in lines if l.startswith("# ")), "")
    if not header:
        errors.append("缺少一级标题（# EPxx …）")

    # ── 总览表 ──
    overview = parse_overview(lines)
    # 只检查总览表区段内的行（15 列）；资产绑定表等其它 5 列表格不受影响
    malformed: list[str] = []
    in_overview = False
    for line in lines:
        if OVERVIEW_HEADER_RE.match(line):
            in_overview = True
            continue
        if not line.startswith("|"):
            in_overview = False
            continue
        if in_overview and OVERVIEW_HEADING_ROW_RE.match(line) and line.count("|") < 15:
            malformed.append(line.strip()[:60])
    if malformed:
        errors.append(f"总览表有 {len(malformed)} 行列数不足 15：{malformed[0]}…")

    # ── 逐镜块：必填行齐全性 ──
    block_ids: list[str] = []
    seen_lines: dict[str, set[str]] = {}
    for line in lines:
        heading = HEADING_RE.match(line)
        if heading:
            shot_id = heading.group(1)
            block_ids.append(shot_id)
            seen_lines.setdefault(shot_id, set())
            continue
        if block_ids:
            for prefix, label in REQUIRED_BLOCK_LINES:
                if line.startswith(prefix):
                    seen_lines[block_ids[-1]].add(label)

    for shot_id in block_ids:
        if shot_id not in overview:
            errors.append(f"{shot_id}：逐镜块存在但总览表缺行")
        missing = [label for _, label in REQUIRED_BLOCK_LINES
                   if label not in seen_lines.get(shot_id, set())]
        if missing:
            errors.append(f"{shot_id}：缺少必填行：{'、'.join(missing)}")
    for shot_id in overview:
        if shot_id not in block_ids:
            errors.append(f"{shot_id}：总览表有行但缺少逐镜块（## {shot_id}）")

    # ── 时长与镜头数 ──
    durations = {sid: s.get("duration") for sid, s in overview.items()}
    total = sum(d for d in durations.values() if d)
    if total != target_duration:
        errors.append(f"总览表时长合计 {total}s ≠ 目标 {target_duration}s")
    for shot_id, duration in durations.items():
        if duration is None:
            continue
        if not (shot_min <= duration <= shot_max):
            errors.append(f"{shot_id}：单镜 {duration}s 超出硬性区间 [{shot_min}, {shot_max}]s")
        elif duration > soft_max:
            warnings.append(f"{shot_id}：单镜 {duration}s 超过建议上限 {soft_max}s"
                            "（多人/长台词镜头建议 ≤6s）")
    count = len(overview)
    if abs(count - expected_shots) > 1:
        errors.append(f"镜头数 {count} 超出规范（{expected_shots}±1）")

    # ── 禁止相对引用 ──
    # 只检查逐镜块内部（规范约束的是镜头内容）；规则文档/质检清单里提到的「同上」不算
    in_block = False
    for line in lines:
        if HEADING_RE.match(line):
            in_block = True
            continue
        if line.startswith("#"):
            in_block = False
            continue
        if in_block and "同上" in line:
            errors.append("逐镜块内出现「同上」（禁止相对引用，必须逐字写全）："
                          + line.strip()[:50])
            break

    # ── 摄影语言与表情词可译性 ──
    parsed = parse_episode(episode, root)
    shots = parsed["shots"]
    unknown_camera: list[str] = []
    unhit_expression: list[str] = []
    pov_shots = 0
    for shot_id, shot in shots.items():
        for key in ("shot_size", "angle", "movement"):
            value = (shot.get(key) or "").strip()
            if value and value not in DASH_SET and value not in CAMERA_PHRASE:
                unknown_camera.append(f"{shot_id}.{key}={value}")
        function_text = shot.get("function_zh", "") + " " + " ".join(shot.get("beats_zh", []))
        if any(tag in function_text for tag in ("POV", "主观", "第一视角")):
            pov_shots += 1
        mood = (shot.get("mood_zh") or "").strip()
        if mood and mood not in DASH_SET and not best_match(mood, EXPRESSION_MAP):
            unhit_expression.append(f"{shot_id}：{mood}")
    if unknown_camera:
        warnings.append("摄影取值不在 CAMERA_PHRASE 内（编译时会被丢弃）："
                        + "；".join(unknown_camera[:8])
                        + ("…" if len(unknown_camera) > 8 else ""))
    if unhit_expression:
        warnings.append("表情词未在 EXPRESSION_MAP 命中（编译时按无表情处理）："
                        + "；".join(unhit_expression[:8])
                        + ("…" if len(unhit_expression) > 8 else ""))
    if pov_shots == 0:
        warnings.append("全集未检出 POV / 主观镜头（规范要求每集至少 1 个）")

    # ── 台词同步 ──
    dialogue_report = check_episode_dialogue(root, episode, parsed=parsed)
    warnings.extend(dialogue_report["issues"])

    return {
        "episode": episode,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "shots": count,
            "total_duration_s": total,
            "target_duration_s": target_duration,
            "shots_with_dialogue": dialogue_report["stats"]["shots_with_dialogue"],
            "pov_shots": pov_shots,
            "header": header,
        },
    }
