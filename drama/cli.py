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
    opendreamina drama review-import [--project ROOT] [--title .. --episodes EP01,EP02 --dry-run]

项目根解析优先级：--project > 环境变量 DRAMA_PROJECT_ROOT > 当前目录。
映射表解析优先级：--maps > 环境变量 DRAMA_MAPS > {项目根}/tools/maps.py（存在才加载）。
"""

from __future__ import annotations

import argparse
import json
import re
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


def _die(message: str, code: int = 2) -> None:
    """错误退出：提示走 stderr，stdout 不输出半成品 JSON。"""
    sys.stderr.write(f"[opendreamina drama] {message}\n")
    raise SystemExit(code)


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
    # 镜头数上下限随目标时长等比推导（90s→18），可用 --expected-shots 显式覆盖（番外等非 90s 集用）
    expected_shots = ns.expected_shots or max(4, round(ns.target_duration / 90 * 18))
    report = lint_episode(root, episode, target_duration=ns.target_duration,
                          expected_shots=expected_shots)
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


def cmd_drama_review_import(ns: argparse.Namespace) -> int:
    """把分镜与生成结果导入审片中心，逐镜建立审片任务卡片。"""
    from drama.review_import import build_import_rows

    root = _project_root(ns)
    title = ns.title or f"{root.name} 分镜生成审片"
    episodes = [e for e in re.split(r"[,\s]+", ns.episodes or "") if e]
    include_prompt = not ns.no_prompt

    api = None
    task_lookup = None
    if include_prompt:
        # 只读查询生成任务，dry-run 也照常执行，保证预演与实际导入的内容一致；
        # 后端不可达时逐条失败即返回 None（review_import 内已吞掉异常），不影响建档。
        api = _api_client()
        task_lookup = lambda task_id: api.request("GET", f"/tasks/{task_id}")  # noqa: E731

    try:
        planned = build_import_rows(
            root,
            drama_title=ns.drama_title,
            episodes=episodes or None,
            task_lookup=task_lookup,
            include_prompt=include_prompt,
        )
    except ValueError as exc:
        _die(f"参数错误：{exc}")
    rows = planned["rows"]

    summary = {
        "project": str(root),
        "title": title,
        "counts": planned["counts"],
        "episodes": planned["episodes"],
        "missing_shots": planned["missing_shots"],
        "skipped_episodes": planned["skipped_episodes"],
    }

    if ns.dry_run:
        summary["dry_run"] = True
        summary["sample"] = rows[:3]
        _note(f"预演：{len(rows)} 个镜头可供导入（未写入后端）")
        _print_json(summary)
        return 0

    # 根目录以后端视角给出：容器里看到的是挂载点，不是宿主机的本地路径
    root_path = _review_root_path(ns, root)
    api = api or _api_client()
    from mcp.client import ApiError

    try:
        session, created = _ensure_review_session(api, title, root_path, ns.scan_existing)
    except ApiError as exc:
        _die(f"创建审片会话失败：{exc}")
    summary["session"] = {
        "id": session["id"],
        "title": session["title"],
        "root_path": session["root_path"],
        "created": created,
    }

    added = updated = skipped = 0
    missing: list[dict] = []
    chunk_size = max(1, ns.chunk_size)
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        try:
            result = api.request(
                "POST",
                f"/shot-reviews/sessions/{session['id']}/items/import",
                json_body={"items": chunk},
                timeout=300,
            )
        except ApiError as exc:
            _die(f"导入第 {start + 1}–{start + len(chunk)} 镜失败（前 {added} 镜已入库）：{exc}")
        added += result.get("added", 0)
        updated += result.get("updated", 0)
        skipped += result.get("skipped", 0)
        missing.extend(result.get("missing") or [])
        _note(f"已导入 {min(start + chunk_size, len(rows))}/{len(rows)} 个镜头卡片")

    summary["import"] = {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "missing": missing[:50],
        "missing_count": len(missing) + len(planned["missing_shots"]),
    }
    final = api.request("GET", f"/shot-reviews/sessions/{session['id']}")
    summary["session"]["item_count"] = final.get("item_count")
    summary["session"]["summary"] = final.get("summary")
    _print_json(summary)
    return 0 if not missing else 1


def _api_client():
    """后端 API 客户端：与主 CLI / MCP 共用 mcp.client（纯标准库）。"""
    from mcp.client import ApiClient

    return ApiClient()


def _review_root_path(ns: argparse.Namespace, project_root: Path) -> str:
    """项目根在后端容器里的路径。

    显式 --root-path 优先；否则按本仓库的部署约定自动映射：项目位于仓库
    ``data/`` 之下时对应容器内的 ``/app/data``（compose 把 ./data 挂到 /app/data）。
    映射不出来就报错，让用户显式给出，绝不猜一个后端可能无权访问的路径。
    """
    if ns.root_path:
        return ns.root_path
    data_dir = Path(__file__).resolve().parent.parent / "data"
    try:
        relative = project_root.resolve().relative_to(data_dir.resolve())
    except ValueError:
        raise SystemExit(
            f"无法推断项目在容器内的路径：{project_root} 不在本仓库 data/ 目录下。\n"
            "请用 --root-path 显式指定（后端视角的绝对路径，如 /app/shot_sources/我的短剧），"
            "并确认该目录已挂载且包含在 SHOT_REVIEW_SOURCE_ROOTS 中。"
        )
    return str(Path("/app/data") / relative)


def _ensure_review_session(api, title: str, root_path: str, scan_existing: bool):
    """复用同名未完成会话，没有则新建（默认不扫描，避免把参考素材收进审片列表）。"""
    sessions = api.request("GET", "/shot-reviews/sessions").get("items") or []
    for session in sessions:
        if session.get("title") == title and session.get("root_path") == root_path:
            _note(f"复用已有审片会话：{session['id']}")
            return session, False
    session = api.request(
        "POST",
        "/shot-reviews/sessions",
        json_body={"title": title, "root_path": root_path},
        query={"scan": "true" if scan_existing else "false"},
        timeout=300,
    )
    _note(f"已创建审片会话：{session['id']}")
    return session, True


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
    p_lint.add_argument("--expected-shots", type=int, default=None,
                        help="单集镜头数基准（默认按时长等比推导：90s→18）。")

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

    p_import = drama_sub.add_parser(
        "review-import", parents=[common],
        help="把分镜与生成结果导入审片中心（逐镜建审片任务卡片）",
        description=(
            "解析 分镜脚本 的逐镜表与 生产状态，把已成片的镜头连同「应有 vs 实际」"
            "（秒数/景别/运镜/台词/生成任务提示词）导入镜头审片，一次导入即可在审片页逐镜打分与提意见。"
            "重复导入按（集号, 镜号, 文件路径）幂等刷新，不会覆盖已打的分与已写的意见。"
        ),
    )
    p_import.add_argument("--title", help="审片会话标题（默认「{项目名} 分镜生成审片」；同名会话会被复用）。")
    p_import.add_argument("--drama-title", help="卡片上的剧目标签（默认不填，前端回落为会话标题）。")
    p_import.add_argument("--episodes", help="只导入指定集，逗号分隔（如 EP01,EP02）；缺省导入全部有成片的集。")
    p_import.add_argument("--root-path", help="项目根在后端容器内的绝对路径（默认按 ./data → /app/data 自动映射）。")
    p_import.add_argument("--no-prompt", action="store_true", help="不拉取生成任务提示词（离线或加速用）。")
    p_import.add_argument("--scan-existing", action="store_true",
                          help="新建会话时先扫描目录（默认不扫描，只导入清单内的镜头，避免收进参考素材）。")
    p_import.add_argument("--chunk-size", type=int, default=100, help="每批提交的镜头数（默认 100）。")
    p_import.add_argument("--dry-run", action="store_true", help="只解析并输出清单摘要，不写入后端。")

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
        "review-import": cmd_drama_review_import,
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
