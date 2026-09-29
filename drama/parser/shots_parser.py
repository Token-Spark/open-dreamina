"""分镜脚本解析器：把 `{项目根}/分镜脚本/EPxx/shots.md` 解析为结构化镜头数据。

从《代号奥林匹斯》shots_parser.py 提取，项目根改为参数传入（不再依赖模块级路径）。

解析出的内容全部来自定稿分镜脚本（不改写）：
  · 总览表        → 时长 / 景别 / 机位 / 运镜（英文摄影语言）
  · 资产绑定行    → 该镜引用的角色 / 场景 / 道具 / 音色资产 ID
  · 人物行        → 出场角色的英文外观锚点（逐字）
  · 场景描述行    → 场景英文锚点（逐字）
  · 台词同步块    → 逐字英文台词 + 说话人 + 口播形式（画面内 / 画外音）

中文叙述字段（光感 / 色调 / 构图 / 细节 / 秒级动作）原样保留在 *_zh 字段中，
由 drama.compiler.prompt_compiler 通过项目映射表翻译为英文。
"""

from __future__ import annotations

import re
from pathlib import Path

from drama.lexicon import (
    LATIN_WORD,
    TRIM_CHARS,
    english_run,
    is_asset_token,
    label_to_english,
    strip_cjk,
)

QUOTE = "\"'“”‘’"
# 标记「该角色不入画」（只作为视点或画外声音存在）
OFFSCREEN_TAGS = ("不入画", "仅作为视点", "画外声音", "画外音")
# 三视图优先：角色槽只保留 *_turnaround（注意事项 6）。
# 置 False 可关闭该过滤（不推荐；会降低多角度一致性）。
CHARACTER_SLOT_TURNAROUND_ONLY = True
CAMERA_PHRASE = {
    # 景别
    "wide": "wide shot", "medium": "medium shot", "close_up": "close-up",
    "extreme_close_up": "extreme close-up", "full": "full shot",
    "medium→close_up": "medium shot settling into a close-up",
    "wide→medium": "wide shot settling into a medium shot",
    # 机位 / 角度
    "eye-level": "eye-level", "low-angle": "low angle", "high-angle": "high angle",
    "slight-high": "slightly high angle", "slight-low": "slightly low angle",
    "overhead": "overhead angle", "ground-level": "ground-level angle",
    "handheld": "handheld",
    # 运镜
    "static": "static camera", "slow-push": "slowly pushing in",
    "slow-pull": "slowly pulling back", "slow-pan": "slowly panning",
    "slow-tilt-up": "slowly tilting up", "slow-tilt-down": "slowly tilting down",
    "handheld-sway": "handheld with a subtle sway",
    "handheld-rotate": "handheld with a slow rotating drift",
    "handheld-track": "handheld tracking", "handheld-pan": "handheld panning",
    "follow": "following the subject", "slow-follow": "slowly following the subject",
    "quick-pan": "quick pan", "slow-motion": "slow motion",
    "快切蒙太奇": "rapid montage cutting", "侧面跟移": "tracking sideways",
}
ASSET_ID_RE = re.compile(r"\b(?:char|scene|prop|crowd|icon|voice)_[a-z0-9_]+\b")
OVERVIEW_HEADING_RE = re.compile(r"^EP\d+-S\d+$")


def _strip_quotes(text: str) -> str:
    return text.strip().strip(QUOTE).strip()


def strip_html_comments(lines: list[str]) -> list[str]:
    """去掉 HTML 注释块（<!-- … -->，可跨多行）。

    模板示例、机器缓存等写在注释里的内容不应被当作镜头块或必填行参与解析与校验。
    """
    out: list[str] = []
    in_comment = False
    for line in lines:
        if in_comment:
            if "-->" in line:
                in_comment = False
                # 注释结束符后若还有内容，保留该行剩余部分
                rest = line.split("-->", 1)[1]
                if rest.strip():
                    out.append(rest)
            continue
        if "<!--" in line:
            before = line.split("<!--", 1)[0]
            if "-->" in line:  # 单行内闭合
                after = line.split("-->", 1)[1]
                merged = before + after
                if merged.strip():
                    out.append(merged)
            else:
                in_comment = True
                if before.strip():
                    out.append(before)
            continue
        out.append(line)
    return out


def parse_overview(lines: list[str]) -> dict[str, dict]:
    """总览表 → {镜号: {duration, shot_size, angle, movement, *_zh}}。"""
    rows: dict[str, dict] = {}
    for line in lines:
        if not line.startswith("| EP") or line.count("|") < 15:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 15 or not OVERVIEW_HEADING_RE.match(cells[0]):
            continue
        shot_id, duration, size, angle, movement = cells[0], cells[1], cells[2], cells[3], cells[4]
        rows[shot_id] = {
            "duration": int(duration),
            "shot_size": size,
            "angle": angle,
            "movement": movement,
            "composition_zh": cells[5],
            "action_zh": cells[6],
            "mood_zh": cells[7],
            "light_zh": cells[8],
            "color_zh": cells[9],
            "env_zh": cells[10],
            "sound_zh": cells[11],
            "dialogue_zh": cells[12],
        }
    return rows


def camera_phrase(overview: dict) -> str:
    """景别 + 机位 + 运镜 → 英文摄影语言。

    未收录取值一律丢弃：总览表偶有中文或非标准写法，直接透传会污染英文提示词。
    """
    parts = [CAMERA_PHRASE.get(overview.get(key, ""), "")
             for key in ("shot_size", "angle", "movement")]
    return ", ".join(part for part in parts if part)


def parse_binding_line(line: str) -> dict[str, list[str]]:
    """资产绑定行 → {角色: [id], 场景: [id], 道具: [id], 音色: [id]}。

    先按 `｜` 切成槽位段，再取每段首个槽位名，避免正文里出现的
    「场景」「道具」等词被误当成新的槽位标记。
    """
    slots: dict[str, list[str]] = {"角色": [], "场景": [], "道具": [], "音色": []}
    for segment in re.split(r"[｜|]", line):
        marker = re.search(r"(角色|场景|道具|音色)", segment)
        if not marker:
            continue
        body = segment[marker.start():]
        asset_ids = ASSET_ID_RE.findall(body)
        if asset_ids:
            if marker.group(1) == "角色" and CHARACTER_SLOT_TURNAROUND_ONLY:
                # 三视图优先：角色槽里只保留 *_turnaround；
                # （ref `char_*_primary/halfbody`）注解里的种子图/半身图一律不进参考。
                asset_ids = [i for i in asset_ids
                             if not i.startswith("char_") or i.endswith("_turnaround")]
            slots[marker.group(1)] = asset_ids
    return slots


def _split_outside_parens(body: str) -> list[str]:
    """按 `；` 切分片段，但括号内的分号不切（锚点后常跟中文夹注，夹注内含分号）。"""
    chunks: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char in "（(":
            depth += 1
        elif char in "）)":
            depth = max(0, depth - 1)
        elif char in "；;" and depth == 0:
            chunks.append("".join(current))
            current = []
            continue
        current.append(char)
    chunks.append("".join(current))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _cast_name(chunk: str) -> str:
    """人物片段 → 英文名：优先括号内的英文名，其次按中文称谓映射，绝不返回中文。"""
    for candidate in re.findall(r"[（(]([^（()）]+)[）)]", chunk):
        head = candidate.split("／")[0].split("/")[0]
        name = strip_cjk(head).strip(TRIM_CHARS)
        # 名字不该是句子：超过 4 个英文词的括号内容视为描述性注记，不是角色名
        if (LATIN_WORD.search(name) and not is_asset_token(name)
                and len(name.split()) <= 4):
            return name
    return label_to_english(re.split(r"——", chunk, 1)[0])


def parse_cast(line: str) -> list[dict]:
    """人物行 → [{name_en, anchor, in_frame}]。

    name_en / anchor 均为纯英文：中文叙述性夹注（如「素材库无对应资产·待补」）
    与素材 ID 引用（如 `char_venus_s2_turnaround`）一律丢弃。
    """
    body = line.split("：", 1)[1] if "：" in line else line
    cast: list[dict] = []
    for chunk in _split_outside_parens(body):
        in_frame = not any(tag in chunk for tag in OFFSCREEN_TAGS)
        described = chunk.split("——", 1)[1] if "——" in chunk else chunk
        anchor = english_run(described)
        name_en = _cast_name(chunk)
        # 既无英文名又无英文锚点 → 纯中文注记，丢弃
        if not name_en and not anchor:
            continue
        cast.append({"name_en": name_en, "anchor": anchor, "in_frame": in_frame})
    return cast


def parse_scene_anchor(line: str) -> str:
    """场景描述行 → 场景英文锚点（「场景锚点」标记后引号内的英文，逐字复用）。

    shots.md 中该标记的写法不统一（`场景锚点：`、`场景锚点·待补`、
    `场景锚点·兜底英文描述`），统一按「标记之后所有含英文的引号内容」提取。
    """
    marker = line.find("场景锚点")
    if marker < 0:
        return ""
    tail = line[marker:]
    quoted = re.findall(r'["“]([^"”]+)["”]', tail)
    return " ".join(q.strip() for q in quoted if LATIN_WORD.search(q))


def parse_dialogue(block: list[str]) -> list[dict]:
    """台词同步块 → [{speaker, form, text, rate}]，form ∈ {spoken, vo}。"""
    lines: list[dict] = []
    for line in block:
        if not line.startswith("- ") or "台词" not in line:
            continue
        label = line.split("（", 1)[0].lstrip("- ").strip()
        rate_match = re.search(r"语速\s*([\d.]+)", line)
        text_match = re.search(r"台词[：:]\s*[" + QUOTE + r"](.+?)[" + QUOTE + r"]\s*[）)]?\s*$", line)
        if not text_match:
            continue
        form = "vo" if any(tag in line for tag in ("画外音", "内心独白", "画外")) else "spoken"
        lines.append({"speaker": label, "form": form, "text": text_match.group(1).strip(),
                      "rate": float(rate_match.group(1)) if rate_match else None})
    return lines


def parse_shots_file(path: Path, episode: str) -> dict:
    """解析指定 shots.md 文件（parse_episode 的路径版入口，便于自定义布局）。"""
    if not path.is_file():
        raise SystemExit(f"分镜文件不存在：{path}")
    lines = strip_html_comments(path.read_text(encoding="utf-8").splitlines())

    overview = parse_overview(lines)
    header = next((l for l in lines if l.startswith("# ")), "")

    shots: dict[str, dict] = {}
    current = ""
    buffer: list[str] = []

    def flush() -> None:
        if not current:
            return
        record = shots[current]
        record["dialogue"] = parse_dialogue(buffer)
        record["beats_zh"] = [l.lstrip("- ").strip() for l in buffer
                              if l.startswith("- ") and "运镜" in l]
        record["sound_zh"] = [l.split("：", 1)[1].strip() for l in buffer
                              if re.match(r"^\*\*(基础环境音|动作触发音|特效音)[：:]\*\*", l)]

    for line in lines:
        heading = re.match(r"^##\s+(EP\d+-S\d+)\s*$", line)
        if heading:
            flush()
            current = heading.group(1)
            shots[current] = {"shot_id": current, "episode": episode}
            buffer = []
            continue
        if not current:
            continue
        buffer.append(line)
        if line.startswith("**资产绑定："):
            shots[current]["assets"] = parse_binding_line(line)
        elif line.startswith("**镜头功能："):
            shots[current]["function_zh"] = line.split("：", 1)[1].strip()
        elif line.startswith("**人物："):
            shots[current]["cast"] = parse_cast(line)
        elif line.startswith("**场景描述："):
            shots[current]["scene_anchor"] = parse_scene_anchor(line)
        elif line.startswith("**台词同步："):
            inline = line.split("：", 1)[1].strip()
            if inline and inline != "无":
                shots[current].setdefault("_inline_dialogue", []).append(inline)
    flush()

    for shot_id, record in shots.items():
        record.update(overview.get(shot_id, {}))
        record["camera"] = camera_phrase(overview.get(shot_id, {}))
        record.setdefault("assets", {"角色": [], "场景": [], "道具": [], "音色": []})
        record.setdefault("cast", [])
        record.setdefault("dialogue", [])
    return {"episode": episode, "header": header, "shots": shots}


def parse_episode(episode: str, project_root: Path) -> dict:
    """解析 `{project_root}/分镜脚本/{episode}/shots.md`。episode 已归一（EP05）。"""
    path = Path(project_root) / "分镜脚本" / episode / "shots.md"
    return parse_shots_file(path, episode)
