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

"""任务业务服务：进度 Redis 缓存 + 状态机校验。

进度写入：worker 调用 set_progress 同时更新 Redis 与 DB（DB 由调用方负责或在此更新）。
SSE 端点从 Redis 高频读取，DB 作为兜底。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any

import redis

from ..config import settings
from ..utils.time_utils import now_iso

# Redis 进度 key 命名
_PROGRESS_KEY = "task:{task_id}:progress"
_STATUS_KEY = "task:{task_id}:status"
_MESSAGE_KEY = "task:{task_id}:message"

# 终态：完成后清理 Redis 临时 key
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
# 可取消的状态
CANCELLABLE_STATUSES = {"pending", "queued", "running"}

# 状态机合法流转
_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"queued", "running", "cancelled"},
    "queued": {"running", "cancelled", "failed"},
    "running": {"completed", "failed", "cancelled"},
    "failed": {"queued"},  # retry
    "completed": set(),
    "cancelled": set(),
}


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in _TRANSITIONS.get(from_status, set())


def assert_transition(from_status: str, to_status: str) -> None:
    if not can_transition(from_status, to_status):
        raise ValueError(
            f"非法状态流转: {from_status} -> {to_status}。"
            f"当前状态 {from_status} 仅可流转到 {sorted(_TRANSITIONS.get(from_status, set()))}"
        )


def set_progress(
    task_id: str,
    status: str,
    progress: int,
    message: str | None = None,
) -> None:
    """写入 Redis 进度缓存（不更新 DB，DB 由 worker/service 显式更新）。"""
    try:
        r = _redis()
        pipe = r.pipeline()
        pipe.set(_PROGRESS_KEY.format(task_id=task_id), str(progress))
        pipe.set(_STATUS_KEY.format(task_id=task_id), status)
        if message is not None:
            pipe.set(_MESSAGE_KEY.format(task_id=task_id), message)
        pipe.execute()
    except Exception:
        # Redis 不可用不应阻断主流程
        pass


def get_progress(task_id: str) -> dict[str, Any]:
    """从 Redis 读取进度。若无则返回空 dict。"""
    try:
        r = _redis()
        pipe = r.pipeline()
        pipe.get(_PROGRESS_KEY.format(task_id=task_id))
        pipe.get(_STATUS_KEY.format(task_id=task_id))
        pipe.get(_MESSAGE_KEY.format(task_id=task_id))
        progress, status, message = pipe.execute()
        if progress is None and status is None:
            return {}
        return {
            "progress": int(progress) if progress is not None else None,
            "status": status,
            "message": message,
        }
    except Exception:
        return {}


def clear_progress(task_id: str) -> None:
    try:
        r = _redis()
        r.delete(
            _PROGRESS_KEY.format(task_id=task_id),
            _STATUS_KEY.format(task_id=task_id),
            _MESSAGE_KEY.format(task_id=task_id),
        )
    except Exception:
        pass


def is_cancelled(task_id: str) -> bool:
    """worker 检查任务是否已被取消。"""
    info = get_progress(task_id)
    return info.get("status") == "cancelled"


def mark_cancelled(task_id: str) -> None:
    """显式标记取消（供 cancel 接口调用，让 worker 通过 Redis 感知）。"""
    set_progress(task_id, "cancelled", 100, "用户已取消")


def task_progress_payload(task_id: str, status: str, progress: int, message: str | None = None) -> dict[str, Any]:
    """构造 SSE progress 事件 data。"""
    payload: dict[str, Any] = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
    }
    if message:
        payload["message"] = message
    return payload


def completed_payload(task_id: str, asset_ids: list[str] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"task_id": task_id, "status": "completed"}
    if asset_ids:
        payload["result_urls"] = [f"/api/v1/assets/{aid}/file" for aid in asset_ids]
        payload["thumbnail_urls"] = [f"/api/v1/assets/{aid}/thumbnail" for aid in asset_ids]
        payload["result_url"] = payload["result_urls"][0]
        payload["thumbnail_url"] = payload["thumbnail_urls"][0]
    return payload


def failed_payload(task_id: str, error: str) -> dict[str, Any]:
    return {"task_id": task_id, "status": "failed", "error": error}


def safe_json_loads(s: str | None, default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def recover_stale_tasks(max_running_seconds: int = 1500) -> int:
    """将长时间卡在 running / pending 状态的任务标记为 failed（孤儿任务恢复）。

    背景：Celery worker 在任务执行中途被杀/崩溃时，run_generation_task 的
    except 块不会执行，DB 状态会永远停留在 running（"生成中"），前端也一直
    显示生成中。正常任务受 task_time_limit（默认 600s）约束，超过该时长仍未
    进入终态即视为异常。

    pending 任务也可能卡死：worker 崩溃或入队后 worker 未启动时，任务会一直
    停留在"排队中"。用 created_at 判断等待时长，超过阈值即标记失败。

    幂等：仅处理 running/pending 状态且超时的任务，可安全地由定时任务 / worker
    启动时重复调用。

    Args:
        max_running_seconds: 允许的最长运行/等待秒数，超过即判定为卡死。

    Returns:
        本次恢复（标记为 failed）的任务数量。
    """
    from ..database import db_session
    from ..models import Task

    cutoff = datetime.now() - timedelta(seconds=max_running_seconds)
    recovered = 0
    # SQLite 在 Docker Desktop 挂载卷上偶发瞬时 disk I/O error（WAL 同步延迟），
    # 重试几次避免恢复机制因瞬时故障失效、任务永久卡在 running/pending。
    for attempt in range(3):
        try:
            with db_session() as db:
                tasks = db.query(Task).filter(
                    Task.status.in_(("running", "pending"))
                ).all()
                for t in tasks:
                    ts_str = t.started_at if t.status == "running" else t.created_at
                    if not ts_str:
                        continue
                    try:
                        dt = datetime.fromisoformat(ts_str)
                        if dt.tzinfo is not None:
                            dt = dt.astimezone().replace(tzinfo=None)
                    except ValueError:
                        try:
                            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            continue
                    if dt >= cutoff:
                        continue
                    t.status = "failed"
                    t.error_msg = (
                        f"任务执行超时（{'运行' if t.status == 'running' else '排队'}"
                        f"超过 {max_running_seconds // 60} 分钟仍未完成），"
                        "可能因 worker 中断导致，已自动标记为失败，请重试"
                    )
                    t.completed_at = now_iso()
                    recovered += 1
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return recovered
