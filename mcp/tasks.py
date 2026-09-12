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

"""任务类工具：状态查询、列表、等待终态、取消与重试。"""
from __future__ import annotations

import time
from typing import Any

from .client import MAX_WAIT_TIMEOUT, ApiClient
from .common import TERMINAL_STATUSES, task_brief

WAIT_INTERVAL_MIN = 1.0


def get_task(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """查询单个任务最新状态。"""
    task = client.request("GET", f"/tasks/{args['task_id']}")
    return task_brief(task, client, {"terminal": task.get("status") in TERMINAL_STATUSES})


def list_tasks(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """分页查询任务列表。"""
    data = client.request(
        "GET",
        "/tasks",
        query={
            "status": args.get("status"),
            "type": args.get("type"),
            "page": args.get("page"),
            "page_size": args.get("page_size"),
        },
    )
    return {
        "total": data.get("total"),
        "page": data.get("page"),
        "page_size": data.get("page_size"),
        "items": [task_brief(t, client) for t in data.get("items", [])],
    }


def wait_task(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """轮询任务直到终态（completed / failed / cancelled）或超时。"""
    interval = max(WAIT_INTERVAL_MIN, float(args.get("interval_seconds") or 3))
    timeout = min(float(args.get("timeout_seconds") or 600), MAX_WAIT_TIMEOUT)
    started = time.monotonic()
    deadline = started + timeout

    while True:
        task = client.request("GET", f"/tasks/{args['task_id']}")
        status = task.get("status")
        elapsed = round(time.monotonic() - started, 1)
        if status in TERMINAL_STATUSES:
            return task_brief(task, client, {"terminal": True, "waited_seconds": elapsed})
        if time.monotonic() >= deadline:
            return task_brief(
                task,
                client,
                {
                    "terminal": False,
                    "timed_out": True,
                    "waited_seconds": elapsed,
                    "message": f"等待超时（{timeout:.0f}s），任务仍处于 {status}；可再次调用 wait_task 继续等待。",
                },
            )
        time.sleep(interval)


def cancel_task(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """取消任务（仅 pending / queued / running 可取消）。"""
    task = client.request("POST", f"/tasks/{args['task_id']}/cancel")
    return task_brief(task, client)


def retry_task(args: dict[str, Any], client: ApiClient) -> dict[str, Any]:
    """重试失败任务（仅 failed 可重试），返回原 task_id。"""
    data = client.request("POST", f"/tasks/{args['task_id']}/retry")
    task = client.request("GET", f"/tasks/{data['task_id']}")
    return task_brief(task, client, {"next": "已重新入队，可用 wait_task 等待。"})
