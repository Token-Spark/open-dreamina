"""英文提示词编译器：把 shots_parser 的结构化镜头数据编译为 Seedance-ready 英文提示词。

从《代号奥林匹斯》prompt_compiler.py 提取：编译骨架通用，
表情 / 光感 / 色调 / 环境 / 动作词库与角色称谓表由项目级 tools/maps.py 注入
（`apply_maps` 加载，词库为空时中文描述原样丢弃并告警，绝不泄漏中文）。

设计原则：
  1. 英文锚点 / 台词 / 摄影语言逐字复用，不做改写
  2. 中文视觉描述（光感 / 色调 / 构图 / 动作 / 表情）通过映射表翻译为英文
  3. 每个镜头的提示词自足可生成（不需要额外上下文）
  4. 全局风格常量不在此追加，由执行层（生成器）统一拼接
"""

from __future__ import annotations

import re
import sys
from typing import Any

from drama import lexicon
from drama.lexicon import CJK_RUN, speaker_to_english

CJK_ANY = CJK_RUN    # 兜底护栏用：匹配任何中文 / 全角字符

# ─────────────── 中文→英文映射表（项目级 tools/maps.py 注入） ───────────────

EXPRESSION_MAP: dict[str, str] = {}
LIGHT_MAP: dict[str, str] = {}
COLOR_MAP: dict[str, str] = {}
ENV_MAP: dict[str, str] = {}
ACTION_FRAGMENTS: dict[str, str] = {}

# 全局风格常量（可选兜底；执行层优先读 assets_manifest.json 的 style 字段）
STYLE: dict[str, str] = {}


def apply_maps(data: dict) -> None:
    """把项目映射表注入编译器（lexicon 的角色称谓表由 drama.lexicon.apply 负责）。"""
    def _clean(mapping: dict) -> dict[str, str]:
        return {str(k): str(v) for k, v in (mapping or {}).items()}

    EXPRESSION_MAP.clear(); EXPRESSION_MAP.update(_clean(data.get("EXPRESSION_MAP")))
    LIGHT_MAP.clear(); LIGHT_MAP.update(_clean(data.get("LIGHT_MAP")))
    COLOR_MAP.clear(); COLOR_MAP.update(_clean(data.get("COLOR_MAP")))
    ENV_MAP.clear(); ENV_MAP.update(_clean(data.get("ENV_MAP")))
    ACTION_FRAGMENTS.clear(); ACTION_FRAGMENTS.update(_clean(data.get("ACTION_FRAGMENTS")))
    STYLE.clear(); STYLE.update(_clean(data.get("STYLE")))


def _best_match(text: str, mapping: dict[str, str]) -> str:
    """在映射表中查找最长匹配的 key；未命中返回空串。"""
    best_key = ""
    for key in mapping:
        if key in text and len(key) > len(best_key):
            best_key = key
    return mapping.get(best_key, "")


best_match = _best_match  # 公开别名（lint 用于检测未命中词）


def translate_expression(text: str) -> str:
    """翻译表情/情绪关键词。

    「—」「无」与空串返回空串（占位符不是"面无表情"，不该误标 neutral）；
    未命中映射表的实词同样返回空串并告警——模型无从翻译的情绪词，
    硬标 neutral 会抹掉表演节拍，宁可不写、让动作文本自己带情绪。
    """
    cleaned = (text or "").strip()
    if not cleaned or cleaned in {"—", "无", "–", "-", "―"}:
        return ""
    result = _best_match(cleaned, EXPRESSION_MAP)
    if not result:
        print(f"[warn] 表情词未命中 EXPRESSION_MAP，按无表情处理：{cleaned}", file=sys.stderr)
    return result


def translate_light(text: str) -> str:
    """翻译光感/灯光描述；未命中返回空串（避免中文泄漏到英文提示词）。"""
    return _best_match(text, LIGHT_MAP)


def translate_color(text: str) -> str:
    """翻译色调描述；未命中返回空串。"""
    return _best_match(text, COLOR_MAP)


def translate_env(text: str) -> str:
    """翻译环境/场景名称；未命中返回空串。"""
    return _best_match(text, ENV_MAP)


def translate_action(text: str) -> str:
    """翻译动作描述（组合匹配）。"""
    parts: list[str] = []
    remaining = text
    for cn, en in sorted(ACTION_FRAGMENTS.items(), key=lambda x: -len(x[0])):
        if cn in remaining:
            parts.append(en)
            remaining = remaining.replace(cn, "")
    return "; ".join(parts) if parts else ""


# ─────────────── 提示词编译主函数 ───────────────


def compile_prompt(shot: dict[str, Any]) -> str:
    """把单个镜头的结构化数据编译为 Seedance-ready 英文提示词。

    输入：shots_parser.parse_episode() 的单镜 dict。
    输出：自足的英文提示词字符串（不含全局风格常量，由执行层追加）。
    """
    camera = shot.get("camera", "")
    cast = shot.get("cast", [])
    scene_anchor = shot.get("scene_anchor", "")
    dialogue = shot.get("dialogue", [])
    overview = {
        "action": shot.get("action_zh", ""),
        "expression": shot.get("mood_zh", ""),
        "light": shot.get("light_zh", ""),
        "color": shot.get("color_zh", ""),
        "env": shot.get("env_zh", ""),
    }

    sections: list[str] = []

    # ① 摄影语言
    if camera:
        sections.append(f"A {camera}.")

    # ② 角色锚点（逐字英文）
    in_frame = [c for c in cast if c.get("in_frame")]
    off_screen = [c for c in cast if not c.get("in_frame")]

    char_parts: list[str] = []
    for member in in_frame:
        name = member.get("name_en", "")
        anchor = member.get("anchor", "")
        if anchor:
            char_parts.append(f"{name}: {anchor}" if name else anchor)
    if char_parts:
        sections.append("Character binding: " + ". ".join(char_parts) + ".")

    # ③ 动作描述（翻译）
    action_en = translate_action(overview["action"])
    expr_en = translate_expression(overview["expression"])
    if action_en and expr_en:
        sections.append(f"{action_en}; expression: {expr_en}.")
    elif action_en:
        sections.append(f"{action_en}.")
    elif expr_en:
        sections.append(f"Expression: {expr_en}.")

    # ④ 场景锚点（逐字英文）
    if scene_anchor:
        sections.append(
            f"Scene: {scene_anchor}. "
            "Keep the architecture, materials and light identical to the scene reference image."
        )

    # ⑤ 台词（逐字英文）
    dialogue_parts: list[str] = []
    for line in dialogue:
        speaker = speaker_to_english(line["speaker"])
        text = line["text"]
        if line["form"] == "vo":
            dialogue_parts.append(
                f'Off-screen voice-over from {speaker}: "{text}"'
            )
        else:
            dialogue_parts.append(
                f'Spoken dialogue from {speaker}: "{text}"'
            )
    if dialogue_parts:
        sections.append(" ".join(dialogue_parts))

    # ⑥ 不入画角色（仅作为视点或声音存在）
    for member in off_screen:
        name = member.get("name_en", "")
        if name:
            sections.append(f"{name} exists only as a viewpoint or off-screen presence, not visible in frame.")

    # ⑦ 光感 + 色调（翻译）
    light_en = translate_light(overview["light"])
    color_en = translate_color(overview["color"])
    visual_parts: list[str] = []
    if light_en:
        visual_parts.append(light_en)
    if color_en:
        visual_parts.append(f"colour palette: {color_en}")
    if visual_parts:
        sections.append(". ".join(visual_parts) + ".")

    # ⑧ 一致性锚句
    if in_frame:
        sections.append(
            "Keep the character's face, hair and clothing identical to the reference image."
        )

    prompt = " ".join(sections)
    # 台词逐字保护：em-dash / 弯引号 / 省略号是台词合法标点，先转 ASCII，
    # 再走中文兜底护栏（CJK_RUN 会把 U+2014 等当分隔符吞掉，导致 sea-girl—I 掉字）
    prompt = (prompt
              .replace("\u2014", " - ").replace("\u2013", "-")
              .replace("\u2018", "'").replace("\u2019", "'")
              .replace("\u201c", '"').replace("\u201d", '"')
              .replace("\u2026", "..."))
    # 兜底护栏：任何漏网中文都不得进入 Seedance 提示词
    return re.sub(r"\s+", " ", CJK_ANY.sub(" ", prompt)).strip()


def _character_keys(asset_id: str) -> set[str]:
    """从素材 ID 提取角色标识（char_venus_s2_turnaround → {'venus'}）。"""
    tokens = set(asset_id.split("_"))
    return {key for key in lexicon.CHARACTER_ALIASES if key in tokens}


def _name_index_for(asset_id: str, names: list[str], taken: set[int]) -> int:
    """把素材 ID 按角色标识匹配到角色名；无角色标识或已被占用则返回 -1。"""
    for key in _character_keys(asset_id):
        for alias in lexicon.CHARACTER_ALIASES[key]:
            for index, name in enumerate(names):
                if index not in taken and alias in name.lower():
                    return index
    return -1


def compile_role_binding(shot: dict[str, Any]) -> str:
    """编译角色绑定行（中文格式，用于提示词尾部与执行层参考清单）。

    归属依据是素材 ID 自带的角色标识（char_venus_* → Venus），而非下标顺序——
    下标配对会在「名数 ≠ 资产数」时把配角资产错挂到主角名下，导致模型张冠李戴。
    无法归属的资产（群像 / 名场面 / 道具）单独列出，不做猜测。
    """
    cast = shot.get("cast", [])
    assets = shot.get("assets", {})
    parts: list[str] = []

    names = [c["name_en"] for c in cast if c.get("name_en")]
    role_ids = assets.get("角色", [])
    voice_ids = list(assets.get("音色", []))

    # char_ 前缀优先占用角色名，避免 icon_ep27_apollo_shame 之类的参考抢走归属
    order = sorted(range(len(role_ids)),
                   key=lambda index: (not role_ids[index].startswith("char_"), index))
    owner: dict[int, int] = {}
    taken: set[int] = set()
    for index in order:
        name_index = _name_index_for(role_ids[index], names, taken)
        if name_index >= 0:
            owner[index] = name_index
            taken.add(name_index)

    claimed_voices: set[str] = set()
    for index, role_id in enumerate(role_ids):
        if index not in owner:
            parts.append(f"@{role_id}")
            continue
        name_index = owner[index]
        refs = [f"@{role_id}"]
        for voice_id in voice_ids:
            if voice_id in claimed_voices:
                continue
            if _name_index_for(voice_id, [names[name_index]], set()) == 0:
                refs.append(f"@{voice_id}")
                claimed_voices.add(voice_id)
        parts.append(f'{names[name_index]}({", ".join(refs)})')

    for voice_id in voice_ids:
        if voice_id not in claimed_voices:
            parts.append(f"@{voice_id}")

    for slot in ("场景", "道具"):
        slot_ids = assets.get(slot, [])
        if slot_ids:
            parts.append(" / ".join(f"@{asset_id}" for asset_id in slot_ids))

    return "；".join(parts) if parts else "无"


def compile_dialogue_line(shot: dict[str, Any]) -> str | None:
    """编译台词为单行字符串（用于报告记录）。"""
    dialogue = shot.get("dialogue", [])
    if not dialogue:
        return None
    parts = []
    for line in dialogue:
        speaker = speaker_to_english(line["speaker"])
        parts.append(f'{speaker}: "{line["text"]}"')
    return " ".join(parts)


def compile_shot_function(shot: dict[str, Any]) -> str:
    """编译镜头功能描述（中文→英文摘要）。"""
    func = shot.get("function_zh", "")
    if "对话" in func or "台词" in func:
        return "dialogue"
    if "反应" in func:
        return "reaction"
    if "Hook" in func or "hook" in func or "起手" in func:
        return "hook establishing shot"
    if "反转" in func or "钩子" in func:
        return "reveal / cliffhanger"
    if "POV" in func or "主观" in func or "第一视角" in func:
        return "first-person POV insert"
    if "建立" in func:
        return "establishing shot"
    if "插入" in func:
        return "insert shot"
    return func or "shot"
