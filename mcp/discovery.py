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

"""目录与系统类工具：提示词模板、Provider、可用模型能力与健康检查。"""
from __future__ import annotations

from typing import Any

from . import catalog, sizes
from .client import ApiClient, ApiError


def list_templates(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """列出提示词模板（category 可选 image / video），供模板化优化提示词。"""
    items = client.request("GET", "/templates", query={"category": args.get("category")}) or []
    return {
        "total": len(items),
        "items": [
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "category": t.get("category"),
                "prompt_text": t.get("prompt_text"),
                "negative_prompt": t.get("negative_prompt"),
                "params": t.get("params"),
            }
            for t in items
        ],
    }


def list_providers(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """列出已配置的 Provider 及其可接入的 slug。"""
    providers = client.request("GET", "/providers") or []
    options = {o["slug"]: o for o in (client.request("GET", "/providers/slug-options") or [])}
    configured = {p.get("slug") for p in providers}

    items = []
    for provider in providers:
        option = options.get(provider.get("slug"), {})
        items.append(
            {
                "id": provider.get("id"),
                "slug": provider.get("slug"),
                "name": provider.get("name"),
                "is_active": provider.get("is_active"),
                "base_url": provider.get("base_url"),
                "api_key_masked": provider.get("api_key_masked"),
                "modes": option.get("modes", []),
                "builtin": option.get("builtin"),
                "configured_models": [
                    m.get("id") for m in (provider.get("config") or {}).get("models", [])
                ],
            }
        )

    return {
        "providers": items,
        "available_slugs": [
            {
                "slug": slug,
                "display_name": option.get("display_name"),
                "modes": option.get("modes", []),
                "configured": slug in configured,
            }
            for slug, option in options.items()
        ],
        "hint": "provider 参数可用 slug（推荐）或 provider id；未配置的 slug 需先在「设置 → 服务管理」录入 API Key。",
    }


def list_models(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """列出可用模型的 slug / 模型 id / 比例 / 分辨率 / 时长能力（含是否已配置）。"""
    mode = args.get("mode")
    warnings: list[str] = []
    configured: set[str] = set()
    try:
        configured = {p.get("slug") for p in (client.request("GET", "/providers") or [])}
    except ApiError as exc:
        warnings.append(f"未能读取已配置 Provider（{exc}），仅返回目录信息。")

    services = catalog.describe_services(mode)
    for service in services:
        service["configured"] = service["slug"] in configured
        service_mode = mode if mode in service.get("modes", []) else (service.get("modes") or ["image"])[0]
        sample_model = args.get("model_id") or (
            service["models"][0]["id"] if service.get("models") else None
        )
        service["capability"] = sizes.describe(service_mode, sample_model)

    if mode in ("image", "video"):
        options = {mode: sizes.describe(mode, args.get("model_id"))}
    else:
        options = {
            "image": sizes.describe("image", args.get("model_id")),
            "video": sizes.describe("video", args.get("model_id")),
        }

    return {
        "services": services,
        "size_options": options,
        "task_types": catalog.task_type_doc(),
        "warnings": warnings,
    }


def get_health(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """检查后端 / 数据库 / Redis / Celery worker 健康状态。"""
    health = client.request("GET", "/system/health")
    warnings = []
    if health.get("worker") != "ok":
        warnings.append("celery-worker 未就绪：生成任务会停留在 pending，请检查 worker 容器。")
    if health.get("redis") != "ok":
        warnings.append("Redis 未就绪：任务无法入队。")
    health["warnings"] = warnings
    return health
