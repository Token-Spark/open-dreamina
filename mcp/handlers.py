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

"""工具实现的统一入口：按领域聚合，供 tools.py 生成工具清单。

各领域实现分文件维护：
- `generate.py`：生成类（图片/视频/通用任务/素材上传）
- `tasks.py`：任务类（查询/等待/取消/重试）
- `conversations.py`：对话类（增删改查）
- `discovery.py`：目录与系统类（模板/Provider/模型/健康检查）
- `payload.py` / `common.py`：共享的入参构造与出参整形

约定：所有 handler 签名统一为 `(args: dict, client: ApiClient) -> dict`，
返回值均为 JSON 可序列化的 dict，字段名与后端保持一致，不做二次重命名。
"""
from __future__ import annotations

from typing import Any, Callable

from .client import ApiClient
from .conversations import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation,
)
from .discovery import get_health, list_models, list_providers, list_templates
from .generate import create_task, generate_image, generate_video, upload_asset
from .tasks import cancel_task, get_task, list_tasks, retry_task, wait_task

Handler = Callable[[dict[str, Any], ApiClient], dict[str, Any]]

HANDLERS: dict[str, Handler] = {
    # 生成类
    "generate_image": generate_image,
    "generate_video": generate_video,
    "create_task": create_task,
    "upload_asset": upload_asset,
    # 任务类
    "get_task": get_task,
    "list_tasks": list_tasks,
    "wait_task": wait_task,
    "cancel_task": cancel_task,
    "retry_task": retry_task,
    # 对话类
    "create_conversation": create_conversation,
    "list_conversations": list_conversations,
    "get_conversation": get_conversation,
    "update_conversation": update_conversation,
    "delete_conversation": delete_conversation,
    # 目录与系统类
    "list_templates": list_templates,
    "list_providers": list_providers,
    "list_models": list_models,
    "get_health": get_health,
}
