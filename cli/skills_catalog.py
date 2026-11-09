#!/usr/bin/env python3
# Copyright 2026 Open Dreamina Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""AIGC 智能体技能目录：让 agent 通过 CLI 自动发现并选择要加载的技能。

事实来源是仓库 `.skills/*/SKILL.md` 的 YAML frontmatter（name / description），
不做第二份清单，新增技能放入目录即自动出现在列表里。

设计约束（与 CLI 其余部分一致）：
- 纯 Python 标准库，零第三方依赖，不需要后端在线；
- 只读扫描，不修改技能文件；
- 输出为可直接序列化为 JSON 的 dict，供智能体解析；
- 支持 `OPEN_DREAMINA_SKILLS_DIR`（os.pathsep 分隔）与 `--skills-dir` 追加外部技能目录，
  默认目录优先级最高，同名技能先到先得。

典型用法（由 cli/opendreamina.py 的 `skills` 子命令调用）：

    discover()          -> 技能元信息列表
    catalog()           -> 列表 + 可注入 system prompt 的 brief 文本
    show("prompt-optimizer") -> 完整 SKILL.md 正文，供 agent 加载
    match("把剧本拆成分镜", skills) -> 按意图排序的推荐结果
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable

SKILL_FILENAME = "SKILL.md"
ENV_SKILLS_DIR = "OPEN_DREAMINA_SKILLS_DIR"
ENV_NO_HINT = "OPEN_DREAMINA_NO_SKILLS_HINT"

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_SKILLS_ROOT = REPO_ROOT / ".skills"

# 扫描外部技能目录时跳过的目录（内置根只扫一层，不会命中这些名字）。
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", ".git", ".venv", "venv", "dist", "build"})
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")
_ASCII_TERM_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")

LOAD_COMMAND = "opendreamina skills <name>"
SELECT_HINT = (
    "先按用户意图从 skills 中选择最匹配的一项，运行 `opendreamina skills <name>` "
    "读取完整 SKILL.md 并加载后再执行生成任务；无需技能时可直接调用 generate。"
)


# ---------------- 目录解析 ----------------


def resolve_roots(extra: Iterable[str | Path] | None = None) -> list[Path]:
    """返回待扫描的技能根目录，按优先级：内置 .skills > 环境变量 > 命令行追加。

    不存在的目录保留在返回值里，便于 catalog 如实报告 roots；扫描时跳过即可。
    """
    candidates: list[Path] = [BUILTIN_SKILLS_ROOT]
    raw = os.environ.get(ENV_SKILLS_DIR, "")
    candidates.extend(Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip())
    candidates.extend(Path(p).expanduser() for p in (extra or []))

    seen: set[str] = set()
    roots: list[Path] = []
    for path in candidates:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            roots.append(path)
    return roots


def _skill_files(root: Path) -> list[Path]:
    """列出一个根目录下的 SKILL.md。内置根只扫一层；其它根允许嵌套。"""
    if not root.is_dir():
        return []
    if root == BUILTIN_SKILLS_ROOT:
        files = sorted(root.glob(f"*/{SKILL_FILENAME}"))
        top = root / SKILL_FILENAME
        if top.is_file():
            files.insert(0, top)
        return files

    files = []
    for path in sorted(root.rglob(SKILL_FILENAME)):
        if any(part in _SKIP_DIRS or part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue
        files.append(path)
    return files


# ---------------- frontmatter 解析 ----------------


def _strip_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


def parse_frontmatter(text: str) -> dict[str, Any]:
    """解析 SKILL.md 顶部的简单 YAML frontmatter。

    只处理 `key: value` 与缩进续行，足够覆盖 name / description / tags / category
    等元数据；不引入 PyYAML（保持零依赖）。列表值支持 `[a, b]` 与逗号分隔。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), None)
    if end is None:
        return {}

    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if match:
            current_key = match.group(1).lower().replace("-", "_")
            data[current_key] = _strip_value(match.group(2))
        elif current_key and (line.startswith(" ") or line.startswith("\t")):
            # 折叠块 / 续行：拼成单行，去掉 YAML 的 `>` / `|` 标记
            chunk = line.strip()
            if chunk in (">", "|", ">-", "|-"):
                continue
            data[current_key] = f"{data[current_key]} {chunk.lstrip('- ')}".strip()

    list_keys = ("tags", "keywords", "categories")
    for key in list_keys:
        value = data.get(key)
        if isinstance(value, str):
            inner = value.strip()
            if inner.startswith("[") and inner.endswith("]"):
                inner = inner[1:-1]
            data[key] = [part.strip().strip("'\"") for part in inner.split(",") if part.strip()]
    for key in ("when_to_use", "when_to_use_zh", "argument_hint"):
        if key in data and not data[key]:
            data.pop(key)
    return data


def _short(text: str, limit: int) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


def _reference_files(skill_path: Path) -> list[str]:
    ref_dir = skill_path.parent / "references"
    if not ref_dir.is_dir():
        return []
    return sorted(
        str(p.relative_to(skill_path.parent)) for p in ref_dir.rglob("*.md") if p.is_file()
    )


def discover(roots: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    """扫描技能目录，返回按 name 排序的元信息列表（不含 SKILL.md 正文）。"""
    items: dict[str, dict[str, Any]] = {}
    for root in roots if roots is not None else resolve_roots():
        for path in _skill_files(Path(root)):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            meta = parse_frontmatter(text)
            name = str(meta.get("name") or path.parent.name).strip().strip("'\"")
            if not name or name in items:  # 先到先得：内置技能优先于外部同名技能
                continue
            description = str(meta.get("description") or "").strip()
            items[name] = {
                "name": name,
                "description": description,
                "dir": path.parent.name,
                "path": str(path),
                "root": str(Path(root)),
                "tags": meta.get("tags") or [],
                "category": meta.get("category") or None,
                "references": _reference_files(path),
                "load_command": f"opendreamina skills {name}",
            }
    return sorted(items.values(), key=lambda item: item["name"])


# ---------------- 供 agent 消费的视图 ----------------


def brief(skills: list[dict[str, Any]], *, max_description: int = 150) -> str:
    """生成可直接注入 agent 上下文的紧凑技能清单。"""
    lines = [
        "Open Dreamina 可用 AIGC 智能体技能（按需选择一项，"
        f"运行 `{LOAD_COMMAND}` 读取完整 SKILL.md 后再执行；无匹配技能时可直接生成）："
    ]
    for item in skills:
        lines.append(f"- {item['name']}：{_short(item['description'], max_description)}")
    return "\n".join(lines)


def catalog(roots: Iterable[Path] | None = None) -> dict[str, Any]:
    """完整清单 payload：机器可读的 skills + 可注入上下文的 brief。"""
    roots_list = list(roots) if roots is not None else resolve_roots()
    skills = discover(roots_list)
    return {
        "ok": True,
        "count": len(skills),
        "skills_roots": [str(r) for r in roots_list],
        "skills": skills,
        "brief": brief(skills),
        "load_command": LOAD_COMMAND,
        "hint": SELECT_HINT,
    }


def show(name: str, roots: Iterable[Path] | None = None) -> dict[str, Any] | None:
    """按技能名（或目录名）返回完整 SKILL.md，供 agent 加载为技能上下文。"""
    skills = discover(roots)
    key = (name or "").strip()
    hit = next(
        (s for s in skills if s["name"].lower() == key.lower() or s["dir"].lower() == key.lower()),
        None,
    )
    if hit is None:
        return None
    path = Path(hit["path"])
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {**hit, "ok": False, "content": "", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "skill": {k: v for k, v in hit.items()},
        "content": content,
        "hint": "以上为该技能完整 SKILL.md，按其内容执行；需要细则时读取 references 中列出的文件。",
    }


def _terms(text: str) -> set[str]:
    """把中英文意图拆成检索词：英文按词、中文按 2-gram（无需分词库）。"""
    lowered = (text or "").lower()
    terms = set(_ASCII_TERM_RE.findall(lowered))
    for run in _CJK_RUN_RE.findall(lowered):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[i : i + 2] for i in range(len(run) - 1))
    return terms


def match(intent: str, skills: list[dict[str, Any]], *, top_n: int = 3) -> list[dict[str, Any]]:
    """按意图给技能打分排序，帮助 agent 在「选择」这一步少走弯路。

    打分是轻量的字面匹配（技能名命中权重更高），只作推荐，不替 agent 做决定；
    所有技能仍完整保留在 catalog 里。
    """
    query_terms = _terms(intent)
    if not query_terms:
        return []
    normalized = intent.lower().replace("-", " ")
    scored: list[dict[str, Any]] = []
    for item in skills:
        haystack = " ".join(
            [item["name"].replace("-", " "), item["description"], " ".join(item["tags"])]
        ).lower()
        matched = sorted(t for t in query_terms if t in haystack)
        if not matched:
            continue
        score = len(matched)
        if item["dir"].replace("-", " ") in normalized or item["name"].replace("-", " ") in normalized:
            score += 5
        scored.append({**item, "score": score, "matched_terms": matched})
    scored.sort(key=lambda entry: (-entry["score"], entry["name"]))
    return scored[: max(1, top_n)]


def hint_line(skills: list[dict[str, Any]] | None = None) -> str:
    """生成命令时打到 stderr 的一行提示（不污染 stdout 的 JSON 结果）。"""
    items = skills if skills is not None else discover()
    if not items:
        return ""
    names = ", ".join(item["name"] for item in items)
    return (
        f"[opendreamina skills] 检测到 {len(items)} 个 AIGC 技能：{names}；"
        f"运行 `opendreamina skills --brief` 查看清单并选择加载"
        f"（可用 {ENV_NO_HINT}=1 关闭本提示）。\n"
    )
