"""中文→英文词汇表与混合文本清洗工具（drama 工具链共享）。

从《代号奥林匹斯》zh_en_lexicon.py 提取：通用清洗规则直接内置，
项目相关映射（角色称谓 / 角色别名 / 表情·光感·色调·动作词库）默认为空，
由项目级 `tools/maps.py` 注入（`opendreamina drama init` 会生成模板）。

设计取向：宁可少一个英文名，也绝不让中文进入 Seedance 提示词。
"""

from __future__ import annotations

import re
from pathlib import Path

# 中文文字 / 中文标点 / 全角符号 / 破折号 / 省略号 / 弯引号 —— 一律视为分隔符
CJK_RUN = re.compile(
    r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef\u2013\u2014\u2018\u2019\u201c\u201d\u2026]+"
)
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
TRIM_CHARS = " \t\r\n*_`'\"(),.;:[]{}/\\-–—、。，；：！？（）【】「」《》"

# 角色名与配角 / 群像称谓 → 英文代称（长键优先匹配，避免「众神」抢走「众神群像」）。
# 项目级 tools/maps.py 注入；长键优先排序在 apply() 中维护。
LABEL_ZH_EN: dict[str, str] = {}

# 素材 ID 里的角色标识 → 角色名别名（用于把 char_venus_s2_turnaround 归属到 Venus）。
# 键取自素材 ID 的 `_` 分段，值是可出现在角色名中的别名（小写）。
CHARACTER_ALIASES: dict[str, tuple[str, ...]] = {}

_LABEL_KEYS_SORTED: list[str] = []


def apply(data: dict) -> None:
    """把项目映射表注入本模块（重复调用以最后一次为准）。"""
    global _LABEL_KEYS_SORTED
    labels = data.get("LABEL_ZH_EN") or {}
    aliases = data.get("CHARACTER_ALIASES") or {}
    LABEL_ZH_EN.clear()
    LABEL_ZH_EN.update({str(k): str(v) for k, v in labels.items()})
    CHARACTER_ALIASES.clear()
    for key, values in aliases.items():
        if isinstance(values, (list, tuple)):
            CHARACTER_ALIASES[str(key)] = tuple(str(v) for v in values)
        else:
            CHARACTER_ALIASES[str(key)] = (str(values),)
    _LABEL_KEYS_SORTED = sorted(LABEL_ZH_EN, key=len, reverse=True)


def load_maps_file(path: Path) -> dict:
    """执行项目映射表文件（tools/maps.py），返回其中声明的全部顶层赋值。

    只取 dict / str 等简单配置值；文件内的函数、导入等会被执行但仅保留
    dict / str 顶层项。文件不存在抛 SystemExit（调用方决定是否降级）。
    """
    if not Path(path).is_file():
        raise SystemExit(f"映射表文件不存在：{path}")
    import runpy

    data = runpy.run_path(str(path))
    return {k: v for k, v in data.items() if isinstance(v, (dict, str, int, float))}


def strip_cjk(text: str) -> str:
    """去掉中文与全角符号，返回纯英文片段。"""
    return re.sub(r"\s+", " ", CJK_RUN.sub(" ", text)).strip()


def english_run(text: str) -> str:
    """从「中文标签 + 英文描述」中取出英文描述片段。

    以英文词数最多的片段为准（锚点通常远长于夹注中的零散英文词），
    并剥掉行首的短标签（如 "A: " / "Hypnos: "）。
    """
    best = ""
    for part in CJK_RUN.split(text):
        candidate = part.strip(TRIM_CHARS)
        if not LATIN_WORD.search(candidate):
            continue
        candidate = re.sub(r"^[A-Za-z]{1,9}\s*:\s*", "", candidate).strip(TRIM_CHARS)
        if len(LATIN_WORD.findall(candidate)) > len(LATIN_WORD.findall(best)):
            best = candidate
    return best


def label_to_english(text: str) -> str:
    """把中文角色 / 配角称谓转为英文代称；未命中返回空串。"""
    for key in _LABEL_KEYS_SORTED:
        if key in text:
            return LABEL_ZH_EN[key]
    return ""


def speaker_to_english(speaker: str) -> str:
    """台词说话人 → 英文；保证绝不返回中文。"""
    for key in _LABEL_KEYS_SORTED:
        if key in speaker:
            return LABEL_ZH_EN[key]
    cleaned = strip_cjk(speaker).strip(TRIM_CHARS)
    if LATIN_WORD.search(cleaned):
        return cleaned
    return "a voice"


def is_asset_token(text: str) -> bool:
    """判断是否为素材 ID（如 scene_garden_primary），而非人物名。"""
    return "_" in text
