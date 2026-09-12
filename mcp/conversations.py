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

"""对话类工具：把多个生成任务按对话分组，便于多轮迭代与追溯。"""
from __future__ import annotations

from typing import Any

from .client import ApiClient
from .common import task_brief


def create_conversation(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """新建对话（用于分组管理多个生成任务）。"""
    return client.request("POST", "/conversations", json_body={"title": args.get("title")})


def list_conversations(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """列出全部对话（含消息数与最后一条提示词）。"""
    return client.request("GET", "/conversations")


def get_conversation(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """查看对话详情；include_messages 为真时附带该对话下的任务列表。"""
    conversation = client.request("GET", f"/conversations/{args['conversation_id']}")
    if args.get("include_messages", True):
        messages = client.request("GET", f"/conversations/{args['conversation_id']}/messages")
        conversation["messages"] = [task_brief(t, client) for t in messages.get("items", [])]
    return conversation


def update_conversation(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """重命名对话。"""
    return client.request(
        "PATCH", f"/conversations/{args['conversation_id']}", json_body={"title": args["title"]}
    )


def delete_conversation(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """删除对话（保留其下任务与生成资产，仅解除分组）。"""
    return client.request("DELETE", f"/conversations/{args['conversation_id']}")
