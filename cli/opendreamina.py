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

"""Open Dreamina 命令行工具：把平台的图片 / 视频生成能力暴露给智能体与脚本。

设计原则：
- 复用 `mcp/` 包的 handler 与目录，保证与 MCP 服务、前端目录同一份事实来源，不重复造轮子。
- 纯 Python 标准库实现，零第三方依赖，宿主机无需 pip install。
- 子命令结构对智能体友好：mode-select 自动推断内容模式、model-select 自动选模型、
  元素引用通过 --reference / --reference-asset 统一处理、progress 子命令轮询进度。

用法：
    python cli/opendreamina.py --help
    python cli/opendreamina.py generate --help
    python cli/opendreamina.py generate --provider seedream --prompt "..." --auto-wait
    python cli/opendreamina.py progress <task_id>
    python cli/opendreamina.py models --mode video
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# 既支持 `python cli/opendreamina.py`（脚本方式），也支持 `python -m cli.opendreamina`（包方式）。
# 把仓库根目录加入 sys.path，统一用绝对导入 mcp.*，避免 cli 与 mcp 互为同级包时
# 相对导入越界（`..mcp` 会越过顶层包）。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from mcp import catalog, sizes, tools as tools_module  # noqa: E402
from mcp.client import ApiClient, ApiError  # noqa: E402

__version__ = "1.0.0"

# ---------------- 输出整形 ----------------


def _print_json(data: Any) -> None:
    """统一以 UTF-8 JSON 输出，便于智能体直接解析。"""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()


def _die(message: str, *, code: int = 1) -> None:
    """向 stderr 输出错误并退出，绝不污染 stdout 的 JSON 流。"""
    sys.stderr.write(f"[opendreamina] {message}\n")
    raise SystemExit(code)


def _call_tool(name: str, args: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    """调用 mcp/ 中注册的工具 handler，统一处理 ApiError 与意外异常。

    返回 (退出码, 结果或错误 dict)。成功时把结果以 JSON 打印到 stdout，
    失败时把错误 dict 打印到 stdout（便于智能体解析）并把人类可读提示打到 stderr。
    """
    try:
        tool = tools_module.validate_call(name, args)
    except (KeyError, ValueError) as exc:
        _die(str(exc))
    try:
        result = tool["handler"](args, ApiClient())
        _print_json(result)
        return 0, result
    except ApiError as exc:
        sys.stderr.write(f"[opendreamina] 后端调用失败：{exc}\n")
        _print_json(exc.to_dict())
        return 2, exc.to_dict()
    except Exception as exc:  # noqa: BLE001 兜底：任何实现缺陷都给可读提示
        sys.stderr.write(f"[opendreamina] 工具 {name} 执行异常：{type(exc).__name__}: {exc}\n")
        return 3, None


def _call_tool_silent(name: str, args: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    """调用工具但不向 stdout 输出，用于需要后续合并结果的场景（如 generate + wait）。"""
    try:
        tool = tools_module.validate_call(name, args)
    except (KeyError, ValueError) as exc:
        _die(str(exc))
    try:
        return 0, tool["handler"](args, ApiClient())
    except ApiError as exc:
        sys.stderr.write(f"[opendreamina] 后端调用失败：{exc}\n")
        return 2, exc.to_dict()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[opendreamina] 工具 {name} 执行异常：{type(exc).__name__}: {exc}\n")
        return 3, None


def _run_tool(name: str, args: dict[str, Any]) -> int:
    """_call_tool 的薄封装，只取退出码，用于不需要读取结果的子命令。"""
    return _call_tool(name, args)[0]


def _download_results(result: dict[str, Any], download_dir: str) -> list[dict[str, Any]]:
    """把任务结果的 result_urls_absolute 下载到本地目录，返回保存清单。

    复用 mcp/client 的 urllib 实现（标准库），按扩展名自动命名；失败项记录 reason。
    """
    import urllib.request
    import urllib.error

    out_dir = Path(download_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    urls = result.get("result_urls_absolute") or []
    saved: list[dict[str, Any]] = []
    for idx, url in enumerate(urls):
        entry: dict[str, Any] = {"url": url, "ok": False}
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - 信任本地后端地址
                raw = resp.read()
            # 从 URL 或 Content-Type 推断扩展名
            ext = Path(url.split("?", 1)[0]).suffix or ""
            if not ext:
                ctype = resp.headers.get("Content-Type", "")
                ext = ".png" if "png" in ctype else (".mp4" if "mp4" in ctype else ".bin")
            task_id = result.get("task_id", "result")
            fname = f"{task_id}_{idx}{ext}"
            (out_dir / fname).write_bytes(raw)
            entry.update(ok=True, path=str((out_dir / fname).resolve()))
        except (urllib.error.URLError, OSError) as exc:
            entry["reason"] = f"{type(exc).__name__}: {exc}"
        saved.append(entry)
    return saved


# ---------------- 参考素材自动审核（对用户透明） ----------------

# 需要参考素材先通过审核的 provider 关键字（Spark Hub Seedance 系列）。
_AUDIT_PROVIDER_HINTS = ("sparkhub-seedance",)

# 提审接口仅接受 Image / Video 两类素材；音频等类型不在提审范围内，
# 直接以公网 URL 参与生成（后端 worker 会把它路由到 audio_urls）。
_AUDITABLE_ASSET_TYPES = frozenset({"image", "video"})


def _needs_audit(provider: str, mode: str) -> bool:
    """判断该 provider + mode 是否需要参考素材先通过审核。

    Spark Hub Seedance 渠道的图生视频（img2video）要求素材先审核通过；
    其余 provider / 模式不需要。判定保守：仅当 video 且 provider 命中关键字时为真。
    """
    if mode != "video":
        return False
    lowered = (provider or "").lower()
    return any(h in lowered for h in _AUDIT_PROVIDER_HINTS)


def _is_auditable(asset: dict[str, Any]) -> bool:
    """判断素材是否需要走提审：仅 Image / Video，音频等类型直接跳过。"""
    return str(asset.get("type") or "").lower() in _AUDITABLE_ASSET_TYPES


def _audit_one_asset(
    provider: str,
    asset_id: str,
    client: ApiClient,
    deadline: float,
    interval: float,
) -> str | None:
    """确保单个图片 / 视频素材审核通过，返回该 asset_id。

    已审核通过（active）直接返回；未审核时提交审核并轮询到终态。
    出错时向 stdout 打印错误 JSON 并返回 None，由调用方终止整个流程。
    """
    import time

    # 查当前审核状态。
    try:
        asset = client.request("GET", f"/assets/{asset_id}/audit", query={"provider": provider})
    except ApiError as exc:
        sys.stderr.write(f"[opendreamina] 查询素材审核状态失败：{exc}\n")
        _print_json(exc.to_dict())
        return None
    status = asset.get("audit_status")
    if status == "active":
        sys.stderr.write(f"[opendreamina] 素材 {asset_id} 已审核通过，跳过。\n")
        return asset_id
    if status != "pending":
        # 非 active / 非 pending（含 None）：提交审核。
        sys.stderr.write(f"[opendreamina] 素材 {asset_id} 未审核，自动提交审核...\n")
        try:
            asset = client.request(
                "POST", f"/assets/{asset_id}/audit", json_body={"provider": provider}
            )
        except ApiError as exc:
            sys.stderr.write(f"[opendreamina] 提交审核失败：{exc}\n")
            _print_json(exc.to_dict())
            return None
        status = asset.get("audit_status")
    # 轮询到 active / failed 或超时。
    while status not in ("active", "failed"):
        if time.monotonic() >= deadline:
            sys.stderr.write(
                f"[opendreamina] 素材 {asset_id} 审核等待超时（仍为 {status}），生成可能失败。\n"
            )
            break
        time.sleep(max(1.0, interval))
        try:
            asset = client.request(
                "GET", f"/assets/{asset_id}/audit", query={"provider": provider}
            )
        except ApiError as exc:
            sys.stderr.write(f"[opendreamina] 查询审核状态失败：{exc}\n")
            _print_json(exc.to_dict())
            return None
        status = asset.get("audit_status")
    if status == "failed":
        err = asset.get("audit_error") or "审核失败"
        sys.stderr.write(f"[opendreamina] 素材 {asset_id} 审核失败：{err}\n")
        _print_json({"error": f"参考素材 {asset_id} 审核失败：{err}，请更换素材重试。"})
        return None
    if status == "active":
        sys.stderr.write(f"[opendreamina] 素材 {asset_id} 审核通过。\n")
    else:
        # 超时仍未通过：仍把 asset_id 交给后端（让后端给出明确错误，而非 CLI 静默失败）。
        sys.stderr.write(
            f"[opendreamina] 素材 {asset_id} 审核未确认（{status}），继续尝试生成。\n"
        )
    return asset_id


def _ensure_assets_audited(
    provider: str,
    reference_asset_ids: list[str],
    reference_paths: list[str],
    client: ApiClient,
    *,
    timeout: int = 120,
    interval: float = 3.0,
) -> list[str] | None:
    """对用户透明地处理参考素材审核，返回可直接用于生成的 asset_id 列表。

    流程：上传本地文件 → 按素材类型分流 → 图片 / 视频提审并等待通过，
    音频等不在提审范围内的类型原样透传（后端会把它路由到 audio_urls）。
    全过程在 stderr 打印进度提示，不污染 stdout 的 JSON 流。
    返回 None 表示出错（已打印错误 JSON），调用方应直接返回。
    """
    import time

    ids: list[str] = list(reference_asset_ids)
    # 先上传本地文件，拿到 asset_id（与 mcp collect_reference_ids 等价，但这里要介入审核）。
    for file_path in reference_paths:
        try:
            asset = client.upload_file(file_path)
        except ApiError as exc:
            sys.stderr.write(f"[opendreamina] 上传参考素材失败：{exc}\n")
            _print_json(exc.to_dict())
            return None
        ids.append(asset["id"])
        sys.stderr.write(f"[opendreamina] 已上传参考素材 {file_path} → asset_id={asset['id']}\n")
    if not ids:
        return []

    deadline = time.monotonic() + timeout
    resolved: list[str] = []
    # dict.fromkeys 去重且保留传入顺序（首尾帧模式下顺序有意义）。
    for asset_id in dict.fromkeys(ids):
        # 先取素材详情确认类型：提审接口仅处理 Image / Video。
        try:
            asset = client.request("GET", f"/assets/{asset_id}")
        except ApiError as exc:
            sys.stderr.write(f"[opendreamina] 查询素材信息失败：{exc}\n")
            _print_json(exc.to_dict())
            return None
        if not _is_auditable(asset):
            sys.stderr.write(
                f"[opendreamina] 素材 {asset_id}（type={asset.get('type')}）"
                "不在提审范围内，跳过审核。\n"
            )
            resolved.append(asset_id)
            continue
        audited = _audit_one_asset(provider, asset_id, client, deadline, interval)
        if audited is None:
            return None
        resolved.append(audited)
    return resolved

# mode 关键字 → 内容模式。用于 mode-select：根据提示词 / 参考素材推断走图片还是视频。
_IMAGE_HINTS = ("图", "image", "img", "picture", "photo", "海报", "插画", "照片", "壁纸")
_VIDEO_HINTS = ("视频", "video", "movie", "动画", "动效", "镜头运动", "运镜")


def _infer_mode(prompt: str | None) -> str:
    """从提示词推断内容模式（image / video），用于 --auto-mode。"""
    text = (prompt or "").lower()
    if any(h in text for h in _VIDEO_HINTS):
        return "video"
    if any(h in text for h in _IMAGE_HINTS):
        return "image"
    return "image"  # 默认图片


def _pick_default_model(provider: str, mode: str) -> str | None:
    """model-select：自动选取该 provider 在指定 mode 下的默认模型 id。

    目录缺失或 provider 未登记时返回 None，由上层决定是否报错。
    """
    try:
        service = catalog.find_service(provider)
    except catalog.CatalogError:
        return None
    if not service:
        return None
    models = catalog.models_for_mode(provider, mode)
    return models[0]["id"] if models else None


def _resolve_provider_and_model(args: argparse.Namespace) -> tuple[str, str | None, str]:
    """处理 --provider / --auto-provider 的取值，返回 (provider, model_id, mode)。

    - --auto-provider：按 mode 选首个已配置且支持该模式的 provider（需查询后端）。
    - --auto-model：未显式给出 --model 时自动取该 provider 的默认模型。
    """
    mode = args.mode or _infer_mode(getattr(args, "prompt", None))

    provider = args.provider
    if not provider and args.auto_provider:
        provider = _auto_pick_provider(mode)

    if not provider:
        _die(
            "缺少 --provider。可用 `opendreamina providers` 查看，或加 --auto-provider 自动选择首个已配置服务。"
        )

    model_id = args.model
    if not model_id and args.auto_model:
        model_id = _pick_default_model(provider, mode)
    return provider, model_id, mode


def _auto_pick_provider(mode: str) -> str | None:
    """auto-provider：查询后端已配置 Provider，取首个支持该 mode 的 slug。"""
    try:
        data = tools_module.HANDLERS["list_providers"]({}, ApiClient())
    except ApiError as exc:
        _die(f"自动选择 provider 失败：{exc}")
    for p in data.get("providers", []):
        if mode in (p.get("modes") or []):
            return p.get("slug")
    _die(f"没有已配置的 Provider 支持 {mode} 模式，请在 Web 界面「设置 → 服务管理」录入。")
    return None  # _die 会退出


# ---------------- 子命令实现 ----------------


def cmd_generate(ns: argparse.Namespace) -> int:
    """生成图片 / 视频：自动推断 mode、可选自动选 provider / model、可选自动等待。"""
    provider, model_id, mode = _resolve_provider_and_model(ns)

    # 合并参考素材 id 与本地路径（元素引用）。
    reference_asset_ids: list[str] = list(ns.reference_asset or [])
    reference_paths: list[str] = list(ns.reference or [])

    # 对用户透明地处理参考素材审核：Spark Hub Seedance 图生视频需素材先审核通过。
    # 这里预先上传本地文件并审核，再把已审核的 asset_id 传给 handler，避免 handler 重新上传未审核素材。
    if _needs_audit(provider, mode) and (reference_asset_ids or reference_paths):
        resolved = _ensure_assets_audited(
            provider, reference_asset_ids, reference_paths, ApiClient()
        )
        if resolved is None:
            return 2
        reference_asset_ids = resolved
        reference_paths = []  # 已上传，不再让 handler 重复上传

    args: dict[str, Any] = {
        "provider": provider,
        "prompt": ns.prompt,
        "model_id": model_id,
        "aspect_ratio": ns.aspect_ratio,
        "resolution": ns.resolution,
        "negative_prompt": ns.negative_prompt,
        "conversation_id": ns.conversation_id,
        "reference_asset_ids": reference_asset_ids or None,
        "reference_paths": reference_paths or None,
    }
    if mode == "video":
        args["duration"] = ns.duration
        args["frame_mode"] = ns.frame_mode
        tool_name = "generate_video"
    else:
        args["count"] = ns.count
        args["steps"] = ns.steps
        args["guidance_scale"] = ns.guidance_scale
        args["seed"] = ns.seed
        args["strength"] = ns.strength
        tool_name = "generate_image"

    # 等待终态：--auto-wait（等待到默认超时）或 --poll=N（等待最多 N 秒，对应即梦 CLI 的 --poll）。
    # 等待时静默提交（不打印初始 task），最终只输出一个 JSON，便于智能体解析。
    poll = getattr(ns, "poll", None)
    wait_enabled = ns.auto_wait or (poll is not None)
    if wait_enabled:
        rc, result = _call_tool_silent(tool_name, args)
        if rc != 0 or not result:
            if result:
                _print_json(result)
            return rc
        task_id = result.get("task_id")
        if not task_id:
            _print_json(result)
            return 0
        timeout = poll if poll is not None else ns.wait_timeout
        sys.stderr.write(
            f"[opendreamina] 已入队 task_id={task_id}，等待完成（最多 {timeout}s）...\n"
        )
        rc2, waited = _call_tool_silent(
            "wait_task",
            {"task_id": task_id, "timeout_seconds": timeout},
        )
        if rc2 != 0 or not waited:
            _print_json(result)
            return rc2
        result = waited
    else:
        rc, result = _call_tool(tool_name, args)
        if rc != 0 or not result:
            return rc

    # --download-dir：终态成功时把结果下载到本地（对应即梦 CLI 的 --download_dir）。
    download_dir = getattr(ns, "download_dir", None)
    if download_dir and result and result.get("status") == "completed":
        saved = _download_results(result, download_dir)
        result = dict(result)
        result["downloaded"] = saved

    # 等待路径下前面未打印，这里统一输出最终结果；非等待路径由 _call_tool 已打印，避免重复。
    if wait_enabled or download_dir:
        _print_json(result)
    return 0


def cmd_progress(ns: argparse.Namespace) -> int:
    """progress：查询任务进度，--wait 时轮询到终态。"""
    if ns.wait:
        return _run_tool(
            "wait_task",
            {
                "task_id": ns.task_id,
                "interval_seconds": ns.interval,
                "timeout_seconds": ns.timeout,
            },
        )
    return _run_tool("get_task", {"task_id": ns.task_id})


def cmd_list_tasks(ns: argparse.Namespace) -> int:
    """tasks：分页查询任务列表，可按状态 / 类型筛选。"""
    return _run_tool(
        "list_tasks",
        {
            "status": ns.status,
            "type": ns.type,
            "page": ns.page,
            "page_size": ns.page_size,
        },
    )


def cmd_cancel(ns: argparse.Namespace) -> int:
    """cancel：取消未完成任务。"""
    return _run_tool("cancel_task", {"task_id": ns.task_id})


def cmd_retry(ns: argparse.Namespace) -> int:
    """retry：重试失败任务。"""
    return _run_tool("retry_task", {"task_id": ns.task_id})


def cmd_query_result(ns: argparse.Namespace) -> int:
    """query_result：查询异步任务结果（对应即梦 CLI 的 query_result）。

    task_id 等价于即梦的 submit_id。--wait 时轮询到终态；--download-dir 时下载结果。
    """
    if ns.wait:
        rc, result = _call_tool(
            "wait_task",
            {
                "task_id": ns.task_id,
                "interval_seconds": ns.interval,
                "timeout_seconds": ns.timeout,
            },
        )
    else:
        rc, result = _call_tool("get_task", {"task_id": ns.task_id})
    if rc != 0 or not result:
        return rc
    if ns.download_dir and result.get("status") == "completed":
        saved = _download_results(result, ns.download_dir)
        result = dict(result)
        result["downloaded"] = saved
        _print_json(result)
    return 0


def make_task_type_command(mode: str, force_reference: bool = False):
    """构造任务类型子命令（text2image / image2image / text2video / image2video / frames2video）。

    复用 cmd_generate，通过预设 ns.mode 与参考素材要求，使命名与即梦 CLI 对齐：
    - text2image / text2video：纯文生图 / 文生视频。
    - image2image / image2video：带参考素材（强制 --reference / --reference-asset）。
    - frames2video：首尾帧驱动视频（强制 --frame-mode first_last 与 2 张参考图）。
    """

    def _handler(ns: argparse.Namespace) -> int:
        ns.mode = mode
        if force_reference and not (ns.reference or ns.reference_asset):
            _die(f"该子命令需要参考素材：请用 --reference <本地路径> 或 --reference-asset <asset_id> 提供。")
        return cmd_generate(ns)

    return _handler


def _frames2video_handler(ns: argparse.Namespace) -> int:
    """frames2video：首尾帧驱动视频，强制 --frame-mode first_last。"""
    ns.mode = "video"
    ns.frame_mode = "first_last"
    if not (ns.reference or ns.reference_asset):
        _die("frames2video 需要 2 张参考图（首帧 + 尾帧）：用 --reference <路径> 传两次。")
    return cmd_generate(ns)



def cmd_upload(ns: argparse.Namespace) -> int:
    """upload：上传本地文件为参考素材，返回 asset_id。"""
    return _run_tool("upload_asset", {"file_path": ns.file_path})


def _audit_brief(asset: dict[str, Any]) -> dict[str, Any]:
    """素材审核字段精简视图（仅保留审核相关字段 + 基本标识）。"""
    return {
        "asset_id": asset.get("id"),
        "type": asset.get("type"),
        "audit_status": asset.get("audit_status"),
        "audit_asset_id": asset.get("audit_asset_id"),
        "audit_asset_url": asset.get("audit_asset_url"),
        "audit_error": asset.get("audit_error"),
        "next": (
            "审核通过（active）后，用 --reference-asset <asset_id> 传给 image2video / frames2video。"
            if asset.get("audit_status") == "active"
            else "审核进行中（pending）或失败（failed）：--wait 可轮询到终态，failed 时请更换素材重新上传。"
        ),
    }


def cmd_audit(ns: argparse.Namespace) -> int:
    """audit：提交/查询参考素材审核（仅 Spark Hub Seedance 生视频需要）。

    后端接口未在 MCP handler 中暴露，这里直接用 ApiClient 调用
    POST/GET /assets/{asset_id}/audit。--wait 时轮询到 active/failed。
    """
    import time

    client = ApiClient()
    asset_id = ns.asset_id
    provider = ns.provider

    # 提交审核（--query-only 时跳过）。--wait 时不立即打印，等终态再统一输出一个 JSON。
    if not ns.query_only:
        try:
            asset = client.request(
                "POST",
                f"/assets/{asset_id}/audit",
                json_body={"provider": provider},
            )
        except ApiError as exc:
            sys.stderr.write(f"[opendreamina] 提交审核失败：{exc}\n")
            _print_json(exc.to_dict())
            return 2
        if asset.get("audit_status") in ("active", "failed"):
            _print_json(_audit_brief(asset))
            return 0
        if not ns.wait:
            _print_json(_audit_brief(asset))
            return 0
        sys.stderr.write(
            f"[opendreamina] 审核已提交（{asset.get('audit_status')}），等待通过（最多 {ns.timeout}s）...\n"
        )

    # 轮询审核状态直到终态（active / failed）或超时。
    deadline = time.monotonic() + ns.timeout
    interval = max(1.0, float(ns.interval))
    while True:
        try:
            asset = client.request(
                "GET", f"/assets/{asset_id}/audit", query={"provider": provider}
            )
        except ApiError as exc:
            sys.stderr.write(f"[opendreamina] 查询审核失败：{exc}\n")
            _print_json(exc.to_dict())
            return 2
        status = asset.get("audit_status")
        if status in ("active", "failed"):
            _print_json(_audit_brief(asset))
            return 0
        if time.monotonic() >= deadline:
            _print_json(_audit_brief(asset))
            return 0
        time.sleep(interval)
        time.sleep(interval)



# ---------------- 目录与系统查询 ----------------


def cmd_models(ns: argparse.Namespace) -> int:
    """models：列出模型目录（slug / 模型 id / 能力），可按 mode 过滤。"""
    return _run_tool("list_models", {"mode": ns.mode, "model_id": ns.model_id})


def cmd_providers(ns: argparse.Namespace) -> int:
    """providers：列出已配置 Provider 与可接入 slug。"""
    return _run_tool("list_providers", {})


def cmd_templates(ns: argparse.Namespace) -> int:
    """templates：列出提示词模板。"""
    return _run_tool("list_templates", {"category": ns.category})


def cmd_health(ns: argparse.Namespace) -> int:
    """health：检查后端 / 数据库 / Redis / worker 健康状态。"""
    return _run_tool("get_health", {})


# ---------------- 对话管理 ----------------


def cmd_conversations(ns: argparse.Namespace) -> int:
    """conversations：对话的增删改查。"""
    action = ns.action
    if action == "list":
        return _run_tool("list_conversations", {})
    if action == "create":
        return _run_tool("create_conversation", {"title": ns.title})
    if action == "get":
        return _run_tool(
            "get_conversation",
            {"conversation_id": ns.id, "include_messages": not ns.no_messages},
        )
    if action == "rename":
        if not ns.title:
            _die("conversations rename 需要 --title")
        return _run_tool(
            "update_conversation", {"conversation_id": ns.id, "title": ns.title}
        )
    if action == "protect":
        if not ns.id:
            _die("conversations protect 需要 --id")
        return _run_tool(
            "update_conversation", {"conversation_id": ns.id, "is_protected": 1}
        )
    if action == "unprotect":
        if not ns.id:
            _die("conversations unprotect 需要 --id")
        return _run_tool(
            "update_conversation", {"conversation_id": ns.id, "is_protected": 0}
        )
    if action == "delete":
        return _run_tool("delete_conversation", {"conversation_id": ns.id})
    _die(f"未知 conversations 动作 {action!r}")
    return 1


# ---------------- 通用任务 ----------------


def cmd_create_task(ns: argparse.Namespace) -> int:
    """create-task：通用任务创建入口，用于 generate 未覆盖的自定义场景。"""
    provider, model_id, mode = _resolve_provider_and_model(ns)
    args: dict[str, Any] = {
        "type": ns.type,
        "provider": provider,
        "model_id": model_id,
        "prompt": ns.prompt,
        "params": json.loads(ns.params) if ns.params else None,
        "aspect_ratio": ns.aspect_ratio,
        "resolution": ns.resolution,
        "negative_prompt": ns.negative_prompt,
        "conversation_id": ns.conversation_id,
        "reference_asset_ids": list(ns.reference_asset or []) or None,
        "reference_paths": list(ns.reference or []) or None,
    }
    return _run_tool("create_task", args)


# ---------------- 参数解析 ----------------


def _add_generate_args(p: argparse.ArgumentParser) -> None:
    """generate / create-task 共用的生成参数。"""
    p.add_argument("--provider", help="模型服务 slug（如 seedream / seedance-2-5 / openai）。可用 providers 查看。")
    p.add_argument("--auto-provider", action="store_true", help="自动选择首个已配置且支持该 mode 的 provider。")
    p.add_argument("--model", help="模型 id，省略则用服务默认模型。可用 models 查看。")
    p.add_argument("--auto-model", action="store_true", help="未显式给出 --model 时，自动取该 provider 的默认模型。")
    p.add_argument("--mode", choices=["image", "video"], help="内容模式；省略则按提示词自动推断（--auto-mode）。")
    p.add_argument("prompt", help="正向提示词（主体 + 场景 + 光线 + 镜头 + 风格）。")
    p.add_argument("--negative-prompt", help="负面提示词，描述要排除的内容。")
    p.add_argument("--aspect-ratio", help=f"画面比例。图片: {'、'.join(sizes.IMAGE_ASPECT_RATIOS)}；视频: {'、'.join(sizes.VIDEO_ASPECT_RATIOS)}。")
    p.add_argument("--resolution", help=f"分辨率档位。图片: {'、'.join(sizes.IMAGE_RESOLUTIONS)}；视频: {'、'.join(sizes.VIDEO_RESOLUTIONS)}。")
    p.add_argument("--reference", action="append", help="本地参考素材路径（可多次传，图片 / 视频 / 音频）。传入后自动切换为图生图 / 图生视频。")
    p.add_argument("--reference-asset", action="append", help="已有素材的 asset_id（可多次传）。")
    p.add_argument("--conversation-id", help="归属对话 id；省略则后端自动新建对话。")
    # 图片专用
    p.add_argument("--count", type=int, help="图片生成张数（1~4，默认 1）。")
    p.add_argument("--steps", type=int, help="图片采样步数（1~80）。")
    p.add_argument("--guidance-scale", type=float, help="提示词权重（1~20，默认 7）。注意后端字段名为 guidance_scale。")
    p.add_argument("--seed", type=int, help="随机种子；显式指定可复现。")
    p.add_argument("--strength", type=float, help="图生图重绘强度（0~1，默认 0.7）。")
    # 视频专用
    p.add_argument("--duration", type=int, help="视频时长（秒）。Seedance 2.5 支持 4~30，Fast/Mini 与 2.0 支持 4~15。")
    p.add_argument("--frame-mode", choices=list(catalog.FRAME_MODES), help="参考图用法：first=首帧；first_last=首尾帧（需 2 张）；reference=内容参考。")
    p.add_argument("--auto-wait", action="store_true", help="生成后自动轮询到终态并打印结果地址。")
    p.add_argument("--poll", type=int, help="生成后等待终态最多 N 秒（对应即梦 CLI 的 --poll）；与 --auto-wait 等价，二者任选其一。")
    p.add_argument("--wait-timeout", type=int, default=600, help="--auto-wait 的等待上限秒数（默认 600，上限 1800）。")
    p.add_argument("--download-dir", help="终态成功时把结果下载到该目录（对应即梦 CLI 的 --download_dir）。")


def build_parser() -> argparse.ArgumentParser:
    """构造子命令解析器；--help 文案即智能体的使用说明。"""
    parser = argparse.ArgumentParser(
        prog="opendreamina",
        description=(
            "Open Dreamina 命令行工具：把平台的图片 / 视频生成能力暴露给智能体与脚本。"
            " 支持 mode-select 自动推断内容模式、model-select 自动选模型、"
            "元素引用（参考素材）、进度查询与等待。输出均为 JSON，便于智能体解析。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "环境变量：\n"
            "  OPEN_DREAMINA_API_BASE     后端 API 基地址（默认 http://localhost:10130/api/v1）\n"
            "  OPEN_DREAMINA_API_TIMEOUT  单次 HTTP 请求超时秒数（默认 60）\n\n"
            "典型工作流：\n"
            "  1) opendreamina health / providers / models  确认环境与可用服务\n"
            "  2) opendreamina generate --provider seedream --prompt '...' --auto-wait\n"
            "  3) opendreamina progress <task_id> --wait    轮询进度或等待终态\n"
            "  4) 读取 result_urls_absolute 下载结果\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"opendreamina {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    # generate
    g = sub.add_parser("generate", help="生成图片 / 视频（自动推断模式）", description="生成图片 / 视频。按 --mode 或提示词推断走图片还是视频；带参考素材自动切换为图生图 / 图生视频。")
    _add_generate_args(g)

    # 任务类型子命令（命名对齐即梦 CLI：text2image / image2image / text2video / image2video / frames2video）
    _task_type_specs = [
        ("text2image", "image", False, "文生图"),
        ("image2image", "image", True, "图生图（带参考素材）"),
        ("text2video", "video", False, "文生视频"),
        ("image2video", "video", True, "图生视频（带参考素材）"),
        ("frames2video", "video", True, "首尾帧驱动视频（需 2 张参考图 + first_last）"),
    ]
    for name, mode, need_ref, desc in _task_type_specs:
        tp_cmd = sub.add_parser(name, help=desc, description=f"{desc}（对应即梦 CLI 同名子命令）。复用 generate 参数。")
        _add_generate_args(tp_cmd)

    # progress
    pr = sub.add_parser("progress", help="查询任务进度（--wait 等待终态）", description="查询单个任务的当前状态与结果地址；--wait 轮询直到终态或超时。")
    pr.add_argument("task_id", help="任务 id（generate / create-task 返回的 task_id）。")
    pr.add_argument("--wait", action="store_true", help="轮询直到终态（completed/failed/cancelled）或超时。")
    pr.add_argument("--interval", type=float, default=3, help="轮询间隔秒数（默认 3，最小 1）。")
    pr.add_argument("--timeout", type=int, default=600, help="等待上限秒数（默认 600，上限 1800）。")

    # query_result（对应即梦 CLI 的 query_result，task_id 等价于 submit_id）
    qr = sub.add_parser("query_result", help="查询异步任务结果（--download-dir 下载）", description="查询异步任务结果（对应即梦 CLI 的 query_result）；task_id 等价于即梦的 submit_id。--wait 轮询到终态；--download-dir 下载结果。")
    qr.add_argument("task_id", help="任务 id（等价于即梦 submit_id）。")
    qr.add_argument("--wait", action="store_true", help="轮询直到终态（completed/failed/cancelled）或超时。")
    qr.add_argument("--interval", type=float, default=3, help="轮询间隔秒数（默认 3，最小 1）。")
    qr.add_argument("--timeout", type=int, default=600, help="等待上限秒数（默认 600，上限 1800）。")
    qr.add_argument("--download-dir", help="终态成功时把结果下载到该目录。")

    # tasks
    lt = sub.add_parser("tasks", help="分页查询任务列表", description="分页查询任务列表，可按状态 / 类型筛选。")
    lt.add_argument("--status", help="按状态筛选，多个用英文逗号分隔（如 pending,running）。")
    lt.add_argument("--type", help="按任务类型筛选（text2img / img2img / text2video / img2video）。")
    lt.add_argument("--page", type=int, default=1, help="页码，从 1 开始（默认 1）。")
    lt.add_argument("--page-size", type=int, default=20, help="每页条数（默认 20，上限 200）。")

    # cancel / retry
    cc = sub.add_parser("cancel", help="取消未完成任务", description="取消尚未完成的任务（仅 pending/queued/running）。")
    cc.add_argument("task_id", help="任务 id。")
    rt = sub.add_parser("retry", help="重试失败任务", description="重试失败的任务（仅 failed），返回重新入队的任务。")
    rt.add_argument("task_id", help="任务 id。")

    # upload
    up = sub.add_parser("upload", help="上传本地文件为参考素材", description="上传本地图片为参考素材，返回 asset_id 供 generate 的 --reference-asset 引用。")
    up.add_argument("file_path", help="本地文件绝对路径。")

    # audit（参考素材审核，仅 Spark Hub Seedance 生视频需要）
    au = sub.add_parser("audit", help="提交/查询参考素材审核（仅 Spark Hub Seedance 生视频需要）", description="提交/查询 Seedance 参考素材审核（Spark Hub seedance_asset_audit）。素材上传后需审核通过（active）才能用于 image2video / frames2video。--wait 轮询到终态。")
    au.add_argument("asset_id", help="待审核的素材 id（upload 返回的 asset_id）。")
    au.add_argument("--provider", required=True, help="Spark Hub Seedance Provider slug（如 sparkhub-seedance）。")
    au.add_argument("--wait", action="store_true", help="提交后轮询直到审核终态（active / failed）或超时。")
    au.add_argument("--query-only", action="store_true", help="只查询不提交（仅调用 GET）。")
    au.add_argument("--interval", type=float, default=3, help="轮询间隔秒数（默认 3，最小 1）。")
    au.add_argument("--timeout", type=int, default=120, help="等待上限秒数（默认 120）。")

    # models / providers / templates / health
    md = sub.add_parser("models", help="列出模型目录", description="列出可用模型的 slug / 模型 id / 比例 / 分辨率 / 时长能力（含是否已配置）。")
    md.add_argument("--mode", choices=["image", "video"], help="只看某一类能力。")
    md.add_argument("--model-id", help="指定模型以查看其精确的分辨率 / 时长能力。")

    pv = sub.add_parser("providers", help="列出已配置 Provider", description="列出已配置的 Provider 与全部可接入 slug（含是否已配置、支持的模式）。")
    tp = sub.add_parser("templates", help="列出提示词模板", description="列出提示词模板（含 prompt_text / negative_prompt / params）。")
    tp.add_argument("--category", choices=["image", "video"], help="按模板分类筛选。")
    hl = sub.add_parser("health", help="检查后端健康状态", description="检查后端 / 数据库 / Redis / Celery worker 健康状态。")

    # conversations
    cv = sub.add_parser("conversations", help="对话的增删改查", description="对话的增删改查：把多个生成任务分组管理。")
    cv.add_argument("action", choices=["list", "create", "get", "rename", "delete", "protect", "unprotect"], help="操作类型。")
    cv.add_argument("--id", help="对话 id（get / rename / delete / protect / unprotect 必填）。")
    cv.add_argument("--title", help="对话标题（create 可选，rename 必填）。")
    cv.add_argument("--no-messages", action="store_true", help="get 时不附带任务列表。")

    # create-task（通用兜底）
    ct = sub.add_parser("create-task", help="通用任务创建入口", description="通用任务创建入口，用于 generate 未覆盖的自定义场景（需完全自定义 type 或 params）。")
    ct.add_argument("--type", required=True, choices=list(catalog.TASK_TYPES), help="任务类型。")
    _add_generate_args(ct)
    # create-task 专用：直接透传给后端的 params 对象（generate 不暴露此参数）。
    ct.add_argument("--params", help="直接透传给后端的参数对象（JSON 字符串）；白名单外的字段会被后端忽略。")

    return parser


_DISPATCH = {
    "generate": cmd_generate,
    "progress": cmd_progress,
    "query_result": cmd_query_result,
    "tasks": cmd_list_tasks,
    "cancel": cmd_cancel,
    "retry": cmd_retry,
    "upload": cmd_upload,
    "audit": cmd_audit,
    "models": cmd_models,
    "providers": cmd_providers,
    "templates": cmd_templates,
    "health": cmd_health,
    "conversations": cmd_conversations,
    "create-task": cmd_create_task,
    # 任务类型子命令（复用 generate 流程，预设 mode / 参考素材要求）
    "text2image": make_task_type_command("image", force_reference=False),
    "image2image": make_task_type_command("image", force_reference=True),
    "text2video": make_task_type_command("video", force_reference=False),
    "image2video": make_task_type_command("video", force_reference=True),
    "frames2video": _frames2video_handler,
}


def main() -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = build_parser()
    ns = parser.parse_args()
    handler = _DISPATCH.get(ns.command)
    if handler is None:  # pragma: no cover - argparse 已保证 command 合法
        parser.error(f"未知命令 {ns.command!r}")
    return handler(ns)


if __name__ == "__main__":
    sys.exit(main())
