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

"""任务路由：CRUD + SSE stream + cancel/retry。"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..database import get_db
from ..models import Conversation, Task
from ..schemas import (
    MessageResponse,
    TaskCreate,
    TaskCreateResponse,
    TaskListResponse,
    TaskResponse,
)
from ..services import task_service
from ..utils.sse import format_event, heartbeat_event
from ..utils.time_utils import now_iso as _now
from ..worker import run_generation_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _to_response(task: Task, asset_ids: list[str] | None = None) -> TaskResponse:
    # 优先使用 worker 落库的有序结果资产 id（多图保序）；旧任务回退到查询到的单个资产。
    params = task_service.safe_json_loads(task.params_json, {})
    stored_ids = params.get("result_asset_ids")
    if isinstance(stored_ids, list) and stored_ids:
        ids = [str(a) for a in stored_ids]
    else:
        ids = asset_ids or []
    result_urls = [f"/api/v1/assets/{aid}/file" for aid in ids]
    thumbnail_urls = [f"/api/v1/assets/{aid}/thumbnail" for aid in ids]
    result_url = result_urls[0] if result_urls else None
    thumbnail_url = thumbnail_urls[0] if thumbnail_urls else None
    # 参考图访问地址：直接由 input_asset_id 派生（与 result_url 同一模式，无需额外查询）
    input_asset_url = (
        f"/api/v1/assets/{task.input_asset_id}/file" if task.input_asset_id else None
    )
    return TaskResponse(
        id=task.id,
        type=task.type,
        status=task.status,
        progress=task.progress,
        provider=task.provider,
        model_id=task.model_id,
        prompt=task.prompt,
        params=params,
        input_asset_id=task.input_asset_id,
        input_asset_url=input_asset_url,
        result_path=task.result_path,
        thumbnail_path=task.thumbnail_path,
        result_url=result_url,
        thumbnail_url=thumbnail_url,
        result_urls=result_urls,
        thumbnail_urls=thumbnail_urls,
        error_msg=task.error_msg,
        api_cost=task.api_cost,
        tokens_used=task.tokens_used,
        retry_count=task.retry_count,
        conversation_id=task.conversation_id,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


def _asset_id_map(db: Session, task_ids: list[str]) -> dict[str, list[str]]:
    """批量查询 task_id -> 有序 asset_id 列表，避免 N+1 查询。"""
    if not task_ids:
        return {}
    from ..models import Asset
    rows = db.query(Asset.id, Asset.task_id).filter(Asset.task_id.in_(task_ids)).all()
    out: dict[str, list[str]] = {}
    for aid, tid in rows:
        if tid:
            out.setdefault(tid, []).append(aid)
    return out


@router.post("", response_model=TaskCreateResponse, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskCreateResponse:
    """创建生成任务，立即入队。"""
    # 将 negative_prompt 合并进 params，供 worker 透传给 Provider
    params = dict(payload.params)
    if payload.negative_prompt:
        params.setdefault("negative_prompt", payload.negative_prompt)

    # 多图参考：完整 ID 列表存入 params 供 worker 读取；
    # 首张写入 input_asset_id 列，兼容旧逻辑（预览 URL 派生、单图回退）。
    input_asset_ids = [aid for aid in (payload.input_asset_ids or []) if aid]
    primary_asset_id = payload.input_asset_id
    if input_asset_ids:
        params["input_asset_ids"] = input_asset_ids
        if not primary_asset_id:
            primary_asset_id = input_asset_ids[0]

    # 归属对话：未指定则自动创建一个，保证任务总有上下文
    conversation_id = payload.conversation_id
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(
                status_code=404,
                detail={"code": "not_found", "message": f"对话 {conversation_id} 不存在"},
            )
    else:
        conv = Conversation(id=str(uuid.uuid4()), title="新对话")
        db.add(conv)
        db.flush()
        conversation_id = conv.id

    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        type=payload.type,
        status="pending",
        progress=0,
        provider=payload.provider,
        model_id=payload.model_id,
        prompt=payload.prompt,
        params_json=json.dumps(params, ensure_ascii=False),
        input_asset_id=primary_asset_id,
        conversation_id=conversation_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 入队 Celery
    try:
        run_generation_task.delay(task_id)
    except Exception as e:
        # 入队失败标记任务 failed，但仍返回 task_id
        task.status = "failed"
        task.error_msg = f"任务入队失败: {e}"
        db.commit()
        db.refresh(task)

    return TaskCreateResponse(task_id=task_id)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: str | None = Query(None, description="逗号分隔的多状态筛选"),
    type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    query = db.query(Task)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            query = query.filter(Task.status.in_(statuses))
    if type:
        query = query.filter(Task.type == type)

    total = query.count()
    items = (
        query.order_by(desc(Task.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    aid_map = _asset_id_map(db, [t.id for t in items])
    return TaskListResponse(
        items=[_to_response(t, aid_map.get(t.id)) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskResponse:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"任务 {task_id} 不存在"})
    aid_map = _asset_id_map(db, [task_id])
    return _to_response(task, aid_map.get(task_id))


def _refresh_task_from_db(task_id: str) -> Task | None:
    """用独立 Session 从 DB 读取任务最新状态。

    worker 完成后会清理 Redis 进度缓存，SSE 端点需要回查 DB 才能感知终态。
    请求级 Session 在长连接中持有旧事务快照，无法看到 worker 的提交，故用独立 Session。
    """
    from ..database import SessionLocal
    with SessionLocal() as s:
        return s.get(Task, task_id)


def _read_status(task_id: str, fallback_task: Task) -> tuple[str, int, str | None]:
    """读取任务状态：优先 Redis，Redis 为空时回查 DB。

    返回 (status, progress, message)。worker 完成后立即清理 Redis，
    此时 DB 已是终态，必须回查 DB 否则 SSE 永远收不到 completed 事件。
    """
    info = task_service.get_progress(task_id)
    if info:
        status = info.get("status") or fallback_task.status
        progress = info.get("progress")
        if progress is None:
            progress = fallback_task.progress
        return status, progress, info.get("message")
    # Redis 已清理：从 DB 读取最新状态
    fresh = _refresh_task_from_db(task_id)
    if fresh:
        return fresh.status, fresh.progress, None
    return fallback_task.status, fallback_task.progress, None


@router.get("/{task_id}/stream")
async def stream_task(task_id: str, request: Request, db: Session = Depends(get_db)):
    """SSE 端点：实时推送任务进度。

    每 15s 发送一次 heartbeat；任务进入终态后立即结束流。
    """
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"任务 {task_id} 不存在"})

    async def event_generator():
        # 立即推送一次当前状态
        status, progress, message = _read_status(task_id, task)

        if status in task_service.TERMINAL_STATUSES:
            yield _terminal_event(task_id, status, task, message)
            return

        yield format_event(
            "progress",
            task_service.task_progress_payload(task_id, status, progress, message),
        )

        last_status = status
        last_progress = progress
        heartbeat_counter = 0
        while True:
            if await request.is_disconnected():
                return

            status, progress, msg = _read_status(task_id, task)

            if status in task_service.TERMINAL_STATUSES:
                yield _terminal_event(task_id, status, task, msg)
                return

            if status != last_status or progress != last_progress:
                yield format_event(
                    "progress",
                    task_service.task_progress_payload(task_id, status, progress, msg),
                )
                last_status = status
                last_progress = progress

            # heartbeat
            heartbeat_counter += 1
            if heartbeat_counter >= settings.sse_heartbeat_interval:
                yield heartbeat_event()
                heartbeat_counter = 0

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _terminal_event(task_id: str, status: str, task: Task, message: str | None) -> str:
    if status == "completed":
        # 查询关联资产 id（优先读 worker 落库的有序结果 id，保序）
        asset_ids: list[str] = []
        try:
            from ..models import Asset
            from ..database import SessionLocal
            with SessionLocal() as s:
                fresh = s.get(Task, task_id)
                if fresh:
                    p = task_service.safe_json_loads(fresh.params_json, {})
                    stored = p.get("result_asset_ids")
                    if isinstance(stored, list) and stored:
                        asset_ids = [str(a) for a in stored]
                if not asset_ids:
                    rows = s.query(Asset.id).filter(Asset.task_id == task_id).all()
                    asset_ids = [r[0] for r in rows]
        except Exception:
            pass
        return format_event("completed", task_service.completed_payload(task_id, asset_ids))
    if status == "failed":
        # message 可能为 None（Redis 已清理走 DB 兜底路径），回查 DB 取最新 error_msg
        err = message
        if not err:
            fresh = _refresh_task_from_db(task_id)
            err = (fresh.error_msg if fresh else None) or "生成失败"
        return format_event("failed", task_service.failed_payload(task_id, err))
    if status == "cancelled":
        return format_event("failed", task_service.failed_payload(task_id, message or "任务已取消"))
    return format_event("progress", task_service.task_progress_payload(task_id, status, task.progress, message))


@router.post("/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(task_id: str, db: Session = Depends(get_db)) -> TaskResponse:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"任务 {task_id} 不存在"})

    if task.status not in task_service.CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_state",
                "message": f"任务当前状态 {task.status} 不可取消",
                "fix": "仅 pending/queued/running 状态可取消",
            },
        )

    # 在 Redis 标记取消，让 worker 自行感知
    task_service.mark_cancelled(task_id)

    task.status = "cancelled"
    task.completed_at = _now()
    db.commit()
    db.refresh(task)
    return _to_response(task)


@router.post("/{task_id}/retry", response_model=TaskCreateResponse)
def retry_task(task_id: str, db: Session = Depends(get_db)) -> TaskCreateResponse:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"任务 {task_id} 不存在"})

    if task.status != "failed":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_state",
                "message": f"仅 failed 任务可重试，当前状态: {task.status}",
            },
        )

    task.status = "queued"
    task.progress = 0
    task.error_msg = None
    task.retry_count = (task.retry_count or 0) + 1
    task.started_at = None
    task.completed_at = None
    db.commit()
    db.refresh(task)

    # 清理旧的进度缓存
    task_service.clear_progress(task_id)

    try:
        run_generation_task.delay(task_id)
    except Exception as e:
        task.status = "failed"
        task.error_msg = f"重试入队失败: {e}"
        db.commit()
        db.refresh(task)

    return TaskCreateResponse(task_id=task_id)


@router.delete("/{task_id}", response_model=MessageResponse)
def delete_task(
    task_id: str,
    delete_files: bool = Query(False, description="是否同时删除关联文件"),
    db: Session = Depends(get_db),
) -> MessageResponse:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"任务 {task_id} 不存在"})

    if delete_files:
        from ..models import Asset
        from ..services.asset_service import delete_asset_files
        assets = db.query(Asset).filter(Asset.task_id == task_id).all()
        for a in assets:
            delete_asset_files(a)
            db.delete(a)

    task_service.clear_progress(task_id)
    db.delete(task)
    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail={"code": "db_error", "message": str(e)})

    return MessageResponse(message=f"任务 {task_id} 已删除", detail={"delete_files": delete_files})
