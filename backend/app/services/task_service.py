"""任务业务服务：进度 Redis 缓存 + 状态机校验。

进度写入：worker 调用 set_progress 同时更新 Redis 与 DB（DB 由调用方负责或在此更新）。
SSE 端点从 Redis 高频读取，DB 作为兜底。
"""
from __future__ import annotations

import json
from typing import Any

import redis

from ..config import settings

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


def completed_payload(task_id: str, asset_id: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"task_id": task_id, "status": "completed"}
    if asset_id:
        payload["result_url"] = f"/api/v1/assets/{asset_id}/file"
        payload["thumbnail_url"] = f"/api/v1/assets/{asset_id}/thumbnail"
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
