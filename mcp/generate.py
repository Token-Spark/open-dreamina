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

"""生成类工具：文生/图生 图片与视频、通用任务创建、参考素材上传。"""
from __future__ import annotations

from typing import Any

from . import catalog, sizes
from .client import ApiClient, ApiError
from .common import absolute_url, compact
from .payload import (
    build_params,
    collect_reference_ids,
    create_and_describe,
    model_warning,
    resolve_size,
)


def generate_image(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """文生图 / 图生图（带参考素材时自动切换为 img2img）。"""
    size = resolve_size("image", args)
    reference_ids, uploaded = collect_reference_ids(args, client)
    task_type = catalog.task_type_for("image", bool(reference_ids))
    warnings = [w for w in [model_warning(args["provider"], args.get("model_id"), task_type)] if w]

    payload = compact(
        {
            "type": task_type,
            "provider": args["provider"],
            "model_id": args.get("model_id"),
            "prompt": args["prompt"],
            "negative_prompt": args.get("negative_prompt"),
            "params": build_params(args, size),
            "input_asset_ids": reference_ids or None,
            "conversation_id": args.get("conversation_id"),
        }
    )
    return create_and_describe(client, payload, size=size, uploaded=uploaded, warnings=warnings)


def generate_video(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """文生视频 / 图生视频（带参考素材时自动切换为 img2video）。"""
    size = resolve_size("video", args)
    reference_ids, uploaded = collect_reference_ids(args, client)

    frame_mode = args.get("frame_mode")
    if frame_mode and frame_mode not in catalog.FRAME_MODES:
        raise ApiError(f"frame_mode 只能是 {list(catalog.FRAME_MODES)} 之一，收到 {frame_mode!r}。")
    if frame_mode and not reference_ids:
        raise ApiError("frame_mode 需要参考素材：请通过 reference_asset_ids 或 reference_paths 提供图片。")
    if frame_mode == "first_last" and len(reference_ids) < 2:
        raise ApiError(f"first_last 需要 2 张参考图（首帧 + 尾帧），当前仅 {len(reference_ids)} 张。")

    duration = args.get("duration")
    if duration is not None and args.get("model_id"):
        spec = sizes.video_duration_range(args["model_id"])
        if not spec["min"] <= int(duration) <= spec["max"]:
            raise ApiError(
                f"模型 {args['model_id']} 的时长范围为 {spec['min']}~{spec['max']} 秒，收到 {duration}。"
            )

    task_type = catalog.task_type_for("video", bool(reference_ids))
    warnings = [w for w in [model_warning(args["provider"], args.get("model_id"), task_type)] if w]

    payload = compact(
        {
            "type": task_type,
            "provider": args["provider"],
            "model_id": args.get("model_id"),
            "prompt": args["prompt"],
            "negative_prompt": args.get("negative_prompt"),
            "params": build_params(args, size, {"frame_mode": frame_mode} if frame_mode else None),
            "input_asset_ids": reference_ids or None,
            "conversation_id": args.get("conversation_id"),
        }
    )
    return create_and_describe(client, payload, size=size, uploaded=uploaded, warnings=warnings)


def create_task(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """通用任务创建：需要完全自定义 type / params 时使用（常规场景用 generate_*）。"""
    task_type = args["type"]
    if task_type not in catalog.TASK_TYPES:
        raise ApiError(f"type 只能是 {list(catalog.TASK_TYPES)} 之一，收到 {task_type!r}。")

    params = dict(args.get("params") or {})
    for key in catalog.PARAM_WHITELIST + ("frame_mode",):
        if key == "negative_prompt":
            continue
        if args.get(key) is not None:
            params[key] = args[key]

    size: dict[str, Any] | None = None
    if args.get("aspect_ratio") or args.get("resolution") or (args.get("width") and args.get("height")):
        size = resolve_size(catalog.mode_of_task_type(task_type), args)
        params["width"], params["height"] = size["width"], size["height"]

    reference_ids, uploaded = collect_reference_ids(args, client)
    payload = compact(
        {
            "type": task_type,
            "provider": args["provider"],
            "model_id": args.get("model_id"),
            "prompt": args.get("prompt"),
            "negative_prompt": args.get("negative_prompt"),
            "params": params,
            "input_asset_ids": reference_ids or None,
            "conversation_id": args.get("conversation_id"),
        }
    )
    return create_and_describe(client, payload, size=size or {}, uploaded=uploaded, warnings=[])


def upload_asset(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """上传本地文件为参考素材，返回 asset_id 供生成任务引用。"""
    asset = client.upload_file(args["file_path"])
    return {
        "asset_id": asset.get("id"),
        "type": asset.get("type"),
        "width": asset.get("width"),
        "height": asset.get("height"),
        "file_url": absolute_url(client, asset.get("file_url")),
        "thumbnail_url": absolute_url(client, asset.get("thumbnail_url")),
        "hint": "把 asset_id 放入 generate_image / generate_video 的 reference_asset_ids；"
        "也可直接用 reference_paths 传本地路径，工具会自动上传。",
    }
