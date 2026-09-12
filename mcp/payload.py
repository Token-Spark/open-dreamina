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

"""生成请求的入参构造与边界校验：把智能体入参翻译成后端 REST 契约。"""
from __future__ import annotations

from typing import Any

from . import catalog, sizes
from .client import ApiClient
from .common import absolute_url, task_brief


def resolve_size(mode: str, args: dict[str, Any]) -> dict[str, Any]:
    """显式 width+height 优先，否则由比例 + 分辨率换算。"""
    width, height = args.get("width"), args.get("height")
    if width and height:
        return {
            "width": int(width),
            "height": int(height),
            "aspect_ratio": args.get("aspect_ratio"),
            "resolution": args.get("resolution"),
        }
    return sizes.resolve_size(mode, args.get("aspect_ratio"), args.get("resolution"))


def collect_reference_ids(args: dict[str, Any], client: ApiClient) -> tuple[list[str], list[dict[str, Any]]]:
    """合并「已有资产 id」与「待上传本地文件」，返回 (asset_ids, 上传结果)。"""
    ids = [str(aid) for aid in (args.get("reference_asset_ids") or []) if aid]
    ids += [str(aid) for aid in (args.get("input_asset_ids") or []) if aid]
    uploaded: list[dict[str, Any]] = []
    for file_path in args.get("reference_paths") or []:
        asset = client.upload_file(file_path)
        ids.append(asset["id"])
        uploaded.append(
            {
                "asset_id": asset["id"],
                "source_path": file_path,
                "file_url": absolute_url(client, asset.get("file_url")),
            }
        )
    # 去重并保序，避免同一素材重复提交
    return list(dict.fromkeys(ids)), uploaded


def build_params(args: dict[str, Any], size: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造后端 params（仅白名单字段），并写入换算后的 width/height。"""
    params: dict[str, Any] = {}
    for key in catalog.PARAM_WHITELIST:
        if key == "negative_prompt":
            continue  # 顶层 negative_prompt 字段已覆盖，避免重复
        value = args.get(key)
        if value is not None:
            params[key] = value
    params["width"] = size["width"]
    params["height"] = size["height"]
    if extra:
        params.update(extra)
    return params


def model_warning(provider: str, model_id: str | None, task_type: str) -> str | None:
    """模型声明不支持该任务类型时给出预警（目录缺失时不阻断）。"""
    if not model_id:
        return None
    service = catalog.find_service(provider)
    if not service:
        return None
    model = next((m for m in service.get("models", []) if m.get("id") == model_id), None)
    if model and task_type not in model.get("types", []):
        return (
            f"模型 {model_id} 在目录中声明的任务类型为 {model.get('types')}，不含 {task_type}；"
            "后端可能返回失败，请确认模型是否支持带/不带参考素材。"
        )
    return None


def create_and_describe(
    client: ApiClient,
    payload: dict[str, Any],
    *,
    size: dict[str, Any],
    uploaded: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    """创建任务并回读一次，返回含 task_id / conversation_id / 下一步动作的说明。"""
    created = client.request("POST", "/tasks", json_body=payload)
    task = client.request("GET", f"/tasks/{created['task_id']}")
    return task_brief(
        task,
        client,
        {
            "size": size,
            "uploaded_references": uploaded,
            "warnings": warnings,
            "next": "任务已入队。用 wait_task 等待完成（推荐），或 get_task 轮询进度。",
        },
    )
