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

"""工具实现共享的辅助函数：出参整形与地址补全。"""
from __future__ import annotations

from typing import Any

from .client import ApiClient

# 任务终态：到达后不再变化，轮询可停止。
TERMINAL_STATUSES = ("completed", "failed", "cancelled")


def compact(mapping: dict[str, Any]) -> dict[str, Any]:
    """剔除 None / 空字符串，避免把空值传给严格校验的后端。"""
    return {key: value for key, value in mapping.items() if value is not None and value != ""}


def absolute_url(client: ApiClient, url: str | None) -> str | None:
    """把后端返回的相对地址（/api/v1/...）补全为可直接下载的绝对地址。"""
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    origin = client.base_url.rsplit("/api/v1", 1)[0]
    return f"{origin}{url}"


def task_brief(task: dict[str, Any], client: ApiClient, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """任务响应精简视图（保留后端字段名，附加可直接下载的绝对地址）。"""
    result_urls = task.get("result_urls") or []
    brief: dict[str, Any] = {
        "task_id": task.get("id"),
        "type": task.get("type"),
        "status": task.get("status"),
        "progress": task.get("progress"),
        "provider": task.get("provider"),
        "model_id": task.get("model_id"),
        "prompt": task.get("prompt"),
        "params": task.get("params"),
        "conversation_id": task.get("conversation_id"),
        "result_urls": result_urls,
        "result_urls_absolute": [absolute_url(client, url) for url in result_urls],
        "thumbnail_urls": task.get("thumbnail_urls") or [],
        "error_msg": task.get("error_msg"),
        "created_at": task.get("created_at"),
        "completed_at": task.get("completed_at"),
    }
    if extra:
        brief.update(extra)
    return brief
