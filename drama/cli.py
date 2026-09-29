"""`opendreamina drama` 子命令组：短剧制作工具链的命令行入口。

由 cli/opendreamina.py 的 build_parser 调用 register_drama_command(sub) 注册，
dispatch(ns) 分发执行。输出约定与主 CLI 一致：stdout 只打 JSON（UTF-8、缩进、
ensure_ascii=False），进度与告警走 stderr，便于智能体解析。

命令清单：

    opendreamina drama init <路径> [--title .. --code .. --episodes 40 --duration 90]
    opendreamina drama list [--project ROOT]
    opendreamina drama parse <EP> [--project ROOT] [--shot S01]
    opendreamina drama compile <EP> [--project ROOT] [--shot S01] [--maps FILE] [--with-style]
    opendreamina drama lint <EP> [--project ROOT] [--maps FILE] [--target-duration 90]
    opendreamina drama spec <EP> [--project ROOT] [--maps FILE] [--write] [--force]
    opendreamina drama assets <EP...|--all> [--project ROOT]
    opendreamina drama manifest [--project ROOT]
    opendreamina drama qc <EP> [--project ROOT] [--min-duration 4] [--aspect 9:16]

项目根解析优先级：--project > 环境变量 DRAMA_PROJECT_ROOT > 当前目录。
映射表解析优先级：--maps > 环境变量 DRAMA_MAPS > {项目根}/tools/maps.py（存在才加载）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from drama import paths as drama_paths


def _print_json(data: Any) -> None:
    """统一以 UTF-8 JSON 输出，便于智能体直接解析（与主 CLI 约定一致）。"""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()


def _note(message: str) -> None:
    sys.stderr.write(f"[opendreamina drama] {message}\n")


# ---------------- 映射表加载 ----------------


def _resolve_maps_path(ns: argparse.Namespace, project_root: Path) -> Path | None:
    import os

    explicit = getattr(ns, "maps", None) or os.environ.get("DRAMA_MAPS")
    if explicit:
        return Path(explicit).expanduser()
    candidate = drama_paths.maps_path(project_root)
    return candidate if candidate.is_file() else None


def load_maps(ns: argparse.Namespace, project_root: Path) -> dict | None:
    """加载并注入项目映射表；返回加载摘要（未配置返回 None）。"""
    from drama.compiler.prompt_compiler import apply_maps
    from drama.lexicon import apply as apply_lexicon, load_maps_file

    path = _resolve_maps_path(ns, project_root)
    if path is None:
        return None
    data = load_maps_file(path)
    apply_lexicon(data)
    apply_maps(data)
    return {
        "path": str(path),
        "labels": len(data.get("LABEL_ZH_EN") or {}),
        "character_aliases": len(data.get("CHARACTER_ALIASES") or {}),
        "expressions": len(data.get("EXPRESSION_MAP") or {}),
        "lights": len(data.get("LIGHT_MAP") or {}),
        "colors": len(data.get("COLOR_MAP") or {}),
        "envs": len(data.get("ENV_MAP") or {}),
        "actions": len(data.get("ACTION_FRAGMENTS") or {}),
    }


def _project_root(ns: argparse.Namespace) -> Path:
    return drama_paths.resolve_project_root(getattr(ns, "project", None))


def _normalize(ns: argparse.Namespace) -> str:
    return drama_paths.normalize_episode(ns.episode)


def _strip_private(node: Any) -> Any:
    """递归去掉以下划线开头的键（解析器内部字段，不进对外输出）。"""
    if isinstance(node, dict):
        return {k: _strip_private(v) for k, v in node.items() if not str(k).startswith("_")}
    if isinstance(node, list):
        return [_strip_private(item) for item in node]
    return node


# ---------------- 各子命令实现 ----------------


def cmd_drama_init(ns: argparse.Namespace) -> int:
    from drama.scaffold.init_project import create_project

    result = create_project(
        ns.path,
        title=ns.title or "",
        code=ns.code or "",
        episodes=ns.episodes,
        duration=ns.duration,
        language=ns.language,
    )
    _note(f"项目骨架已就绪：{result['project_root']}（新建 {len(result['created'])} 项，"
          f"跳过已有 {len(result['skipped'])} 项）")
    _print_json(result)
    return 0


def cmd_drama_list(ns: argparse.Namespace) -> int:
    root = _project_root(ns)
    episodes: list[dict] = []
    for entry in drama_paths.list_episodes(root):
        info = dict(entry)
        if entry["shots_md"]:
            try:
                from drama.parser.shots_parser import parse_episode

                parsed = parse_episode(entry["episode"], root)
                info["shots"] = len(parsed["shots"])
                info["duration_s"] = sum(s.get("duration") or 0 for s in parsed["shots"].values())
            except SystemExit:
                info["shots"] = None
                info["duration_s"] = None
        renders_dir = drama_paths.video_renders_dir(root, entry["episode"])
        if renders_dir.is_dir():
            count = 0
            for candidate in renders_dir.rglob("*.mp4"):
                relative = candidate.relative_to(renders_dir)
                if not any(part.startswith("_") for part in relative.parts):
                    count += 1
            info["render_files"] = count
        else:
            info["render_files"] = 0
        info["spec"] = drama_paths.episode_specs_dir(root).joinpath(
            f"{entry['episode']}.json").is_file()
        episodes.append(info)
    _print_json({"project": str(root), "episodes": episodes})
    return 0


def cmd_drama_parse(ns: argparse.Namespace) -> int:
    root = _project_root(ns)
    episode = _normalize(ns)
    from drama.parser.shots_parser import parse_episode

    load_maps(ns, root)
    data = parse_episode(episode, root)
    shots = data["shots"]
    if ns.shot:
        key = ns.shot.upper()
        shots = {k: v for k, v in shots.items() if k.endswith(key)}
        if not shots:
            _note(f"未找到镜号 {ns.shot}（集内镜号：{', '.join(data['shots'])}）")
    _print_json({"episode": episode, "header": data["header"], "shots": _strip_private(shots)})
    return 0


def cmd_drama_compile(ns: argparse.Namespace) -> int:
    from drama.compiler.prompt_compiler import STYLE, compile_prompt
    from drama.manifest.assets_manifest import load_manifest, style_constants
    from drama.parser.shots_parser import parse_episode

    root = _project_root(ns)
    episode = _normalize(ns)
    maps_summary = load_maps(ns, root)
    parsed = parse_episode(episode, root)

    style: dict[str, str] = {}
    if ns.with_style:
        # manifest.style 优先，maps.py 的 STYLE 兜底（详见 assets_manifest.style_constants）
        style = style_constants(load_manifest(root))
        for key, value in STYLE.items():
            if value and not style.get(key):
                style[key] = value

    prompts: dict[str, str] = {}
    for shot_id, shot in parsed["shots"].items():
        if ns.shot and not shot_id.endswith(ns.shot.upper()):
            continue
        prompt = compile_prompt(shot)
        if ns.with_style:
            tail = ". ".join(part for part in (
                style.get("AESTHETIC", ""), style.get("MEDIUM", ""), style.get("AUDIO", "")) if part)
            if tail:
                prompt = f"{prompt} {tail}."
        prompts[shot_id] = prompt
    if not prompts:
        _note(f"未找到镜号 {ns.shot}（集内镜号：{', '.join(parsed['shots'])}）")
        return 1
    result: dict[str, Any] = {
        "episode": episode,
        "maps_loaded": maps_summary,
        "prompts": prompts,
    }
    if ns.with_style:
        result["style"] = style
        result["negative"] = style.get("NEGATIVE", "")
    _print_json(result)
    return 0


def cmd_drama_lint(ns: argparse.Namespace) -> int:
    from drama.lint.shots_lint import lint_episode

    root = _project_root(ns)
    episode = _normalize(ns)
    load_maps(ns, root)
    report = lint_episode(root, episode, target_duration=ns.target_duration)
    _print_json(report)
    return 0 if report["valid"] else 1


def cmd_drama_spec(ns: argparse.Namespace) -> int:
    from drama.compiler.prompt_compiler import compile_prompt
    from drama.manifest.episode_spec import (
        build_episode_spec,
        validate_episode_spec,
        write_episode_spec,
    )
    from drama.parser.shots_parser import parse_episode

    root = _project_root(ns)
    episode = _normalize(ns)
    maps_summary = load_maps(ns, root)
    parsed = parse_episode(episode, root)
    compiled = {shot_id: compile_prompt(shot) for shot_id, shot in parsed["shots"].items()}
    spec, warnings = build_episode_spec(root, episode, compiled_prompts=compiled)
    validation = validate_episode_spec(spec)
    result: dict[str, Any] = {
        "episode": episode,
        "maps_loaded": maps_summary,
        "spec": spec,
        "warnings": warnings,
        "validation_errors": validation,
        "valid": len(validation) == 0,
    }
    if ns.write:
        path = write_episode_spec(root, episode, spec, force=ns.force)
        result["written"] = str(path)
        _note(f"已写入分集规格：{path}")
    _print_json(result)
    return 0 if result["valid"] else 1


def cmd_drama_assets(ns: argparse.Namespace) -> int:
    from drama.qc.audit_refs import audit_episode_refs

    root = _project_root(ns)
    if ns.all:
        episodes = [e["episode"] for e in drama_paths.list_episodes(root) if e["shots_md"]]
        if not episodes:
            _note("项目下没有可解析的集（分镜脚本/EPxx/shots.md）")
            return 1
    else:
        episodes = [drama_paths.normalize_episode(item) for item in ns.episodes]
    report = audit_episode_refs(root, episodes)
    problems = sum(len(e["missing_platform_id"]) + len(e["missing_files"])
                   for e in report["episodes"])
    _note(f"引用审计完成：{len(episodes)} 集，缺平台 ID / 文件问题 {problems} 项")
    _print_json(report)
    return 0


def cmd_drama_manifest(ns: argparse.Namespace) -> int:
    from drama.manifest.assets_manifest import (
        load_manifest,
        style_constants,
        validate_manifest,
    )
    from drama.manifest.voice_manifest import load_voice_manifest, validate_voice_manifest

    root = _project_root(ns)
    manifest = load_manifest(root)
    voice = load_voice_manifest(root)
    assets_report = validate_manifest(manifest)
    voice_errors = validate_voice_manifest(voice)
    result = {
        "project": str(root),
        "valid": not assets_report["errors"] and not voice_errors,
        "assets_manifest": {
            "path": str(drama_paths.tools_dir(root) / "assets_manifest.json"),
            "exists": manifest is not None,
            "asset_count": len((manifest or {}).get("assets", [])),
            "provider": (manifest or {}).get("provider", ""),
            "model": (manifest or {}).get("model", ""),
            "style": style_constants(manifest),
            "errors": assets_report["errors"],
            "warnings": assets_report["warnings"],
        },
        "voice_manifest": {
            "path": str(drama_paths.tools_dir(root) / "voice_manifest.json"),
            "exists": voice is not None,
            "voice_count": len((voice or {}).get("voices", [])),
            "errors": voice_errors,
        },
    }
    _print_json(result)
    return 0 if result["valid"] else 1


def cmd_drama_qc(ns: argparse.Namespace) -> int:
    from drama.qc.audit_renders import audit_episode_renders

    root = _project_root(ns)
    episode = _normalize(ns)
    report = audit_episode_renders(root, episode, min_duration=ns.min_duration,
                                   aspect=ns.aspect)
    _print_json(report)
    return 0 if report["summary"]["failed"] == 0 else 1


# ---------------- 注册与分发 ----------------


def register_drama_command(sub) -> None:
    """向主 CLI 的 subparsers 注册 `drama` 命令组。"""
    parser = sub.add_parser(
        "drama",
        help="短剧制作工具链（分镜解析 / 提示词编译 / 规范校验 / 规格 / 资产 / 质检）",
        description=(
            "短剧制作工具链：从《代号奥林匹斯》实战项目提炼的通用能力。"
            "输出均为 JSON，便于智能体解析；项目根用 --project 指定"
            "（默认 $DRAMA_PROJECT_ROOT 或当前目录）。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "典型工作流：\n"
            "  1) opendreamina drama init ./我的短剧 --title 剧名   建项目骨架\n"
            "  2) opendreamina drama lint EP01 --project ./我的短剧   校验分镜规范\n"
            "  3) opendreamina drama compile EP01 --project ./我的短剧   编译英文提示词\n"
            "  4) opendreamina drama spec EP01 --project ./我的短剧 --write   生成分集规格\n"
            "  5) opendreamina drama assets EP01 --project ./我的短剧   核对资产引用\n"
            "  6) 生成后：opendreamina drama qc EP01 --project ./我的短剧   成片技术验收\n"
        ),
    )
    drama_sub = parser.add_subparsers(dest="drama_action", metavar="<action>", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", help="短剧项目根目录（默认 $DRAMA_PROJECT_ROOT 或当前目录）。")
    common.add_argument("--maps", help="项目映射表文件（默认 $DRAMA_MAPS 或 {项目根}/tools/maps.py）。")

    p_init = drama_sub.add_parser(
        "init", parents=[common],
        help="初始化标准短剧项目骨架", description="生成标准目录树与模板文件；已存在的文件跳过，可重复执行补齐。")
    p_init.add_argument("path", help="项目根目录（不存在会创建）。")
    p_init.add_argument("--title", help="剧名（默认取目录名）。")
    p_init.add_argument("--code", help="项目代号（默认取目录名）。")
    p_init.add_argument("--episodes", type=int, default=40, help="总集数（默认 40）。")
    p_init.add_argument("--duration", type=int, default=90, help="单集目标时长秒数（默认 90）。")
    p_init.add_argument("--language", default="中文", help="对白语言（默认中文）。")

    p_list = drama_sub.add_parser(
        "list", parents=[common], help="列出项目全部集与状态",
        description="扫描 分镜脚本/ 下的 EPxx 目录，汇总镜头数、时长、渲染文件数与规格状态。")

    p_parse = drama_sub.add_parser(
        "parse", parents=[common], help="解析分镜脚本为结构化 JSON",
        description="解析 分镜脚本/EPxx/shots.md → 镜头结构化数据（锚点逐字保留，中文叙述原样输出）。")
    p_parse.add_argument("episode", help="集号（EP05 / 05 / 5 均可）。")
    p_parse.add_argument("--shot", help="只看某镜（如 S01）。")

    p_compile = drama_sub.add_parser(
        "compile", parents=[common], help="编译镜头英文提示词",
        description="把结构化中文镜头描述编译为 Seedance-ready 英文提示词（映射表由 tools/maps.py 提供）。")
    p_compile.add_argument("episode", help="集号。")
    p_compile.add_argument("--shot", help="只编译某镜（如 S01）。")
    p_compile.add_argument("--with-style", action="store_true",
                           help="把全局风格常量（AESTHETIC/MEDIUM/AUDIO）追加到每条提示词尾部。")

    p_lint = drama_sub.add_parser(
        "lint", parents=[common], help="校验分镜脚本格式规范",
        description="按分镜模板规范校验：总览表 / 必填行 / 时长 / 镜头数 / 相对引用 / 词库命中 / 台词。")
    p_lint.add_argument("episode", help="集号。")
    p_lint.add_argument("--target-duration", type=int, default=90,
                        help="单集目标时长秒数（默认 90）。")

    p_spec = drama_sub.add_parser(
        "spec", parents=[common], help="生成分集执行规格（episode_spec）",
        description="分镜脚本 + manifest + 注册表 → tools/episode_specs/EPxx.json（数据/机制分离的生成输入）。")
    p_spec.add_argument("episode", help="集号。")
    p_spec.add_argument("--write", action="store_true", help="写入 tools/episode_specs/EPxx.json。")
    p_spec.add_argument("--force", action="store_true", help="目标规格已存在时覆盖。")

    p_assets = drama_sub.add_parser(
        "assets", parents=[common], help="资产引用与平台 asset_id 比对",
        description="扫描分镜引用的资产 ID，核对 manifest 登记与平台 asset_id，缺引用即无参考生成风险。")
    p_assets.add_argument("episodes", nargs="*", help="集号（可多个）。")
    p_assets.add_argument("--all", action="store_true", help="审计项目下全部集。")

    p_manifest = drama_sub.add_parser(
        "manifest", parents=[common], help="校验项目级 manifest",
        description="校验 tools/assets_manifest.json 与 tools/voice_manifest.json 的完整性与一致性。")

    p_qc = drama_sub.add_parser(
        "qc", parents=[common], help="成片技术验收（画幅/时长/音轨）",
        description="逐镜核对 video_renders 成片：文件唯一性 / 画幅 / 时长 / 音轨（依赖 ffprobe，缺失时降级）。")
    p_qc.add_argument("episode", help="集号。")
    p_qc.add_argument("--min-duration", type=int, default=4, help="模型最短时长秒数（默认 4）。")
    p_qc.add_argument("--aspect", default="9:16", help="目标画幅（默认 9:16）。")

    handlers = {
        "init": cmd_drama_init,
        "list": cmd_drama_list,
        "parse": cmd_drama_parse,
        "compile": cmd_drama_compile,
        "lint": cmd_drama_lint,
        "spec": cmd_drama_spec,
        "assets": cmd_drama_assets,
        "manifest": cmd_drama_manifest,
        "qc": cmd_drama_qc,
    }
    for action, handler in handlers.items():
        drama_sub.choices[action].set_defaults(drama_func=handler)


def dispatch(ns: argparse.Namespace) -> int:
    """`opendreamina drama <action>` 的入口（由 cli/opendreamina.py 调用）。"""
    handler = getattr(ns, "drama_func", None)
    if handler is None:  # pragma: no cover - argparse 已保证 action 合法
        return 2
    return handler(ns)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - 独立调试入口
    """独立调试入口：python -m drama.cli <action> …（等价于 opendreamina drama <action>）。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m drama.cli")
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)
    register_drama_command(sub)
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if args and args[0] != "drama":
        args.insert(0, "drama")  # 兼容省略 drama 前缀的直接调用
    ns = parser.parse_args(args)
    return dispatch(ns)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
