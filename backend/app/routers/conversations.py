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

"""对话路由：CRUD + 对话内任务列表。

对话是任务的有序分组（按 created_at 排序）。删除对话时仅解除分组，
保留任务记录与生成资产（参见需求4「保留任务」策略）。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Task
from ..schemas import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageResponse,
    TaskListResponse,
    TaskResponse,
)
from .tasks import _asset_id_map, _to_response

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _conv_to_response(c: Conversation) -> ConversationResponse:
    """构建对话响应，附带消息数与最后一条消息的预览信息。"""
    ordered = sorted(c.tasks, key=lambda t: t.created_at)
    last = ordered[-1] if ordered else None
    last_thumbnail_url = None
    if last and last.thumbnail_path:
        # 任务关联资产缩略图 URL
        for a in last.assets:
            if a.thumbnail_path:
                last_thumbnail_url = f"/api/v1/assets/{a.id}/thumbnail"
                break
    return ConversationResponse(
        id=c.id,
        title=c.title,
        created_at=c.created_at,
        updated_at=c.updated_at,
        message_count=len(ordered),
        last_prompt=last.prompt if last else None,
        last_thumbnail_url=last_thumbnail_url,
    )


@router.get("", response_model=ConversationListResponse)
def list_conversations(db: Session = Depends(get_db)) -> ConversationListResponse:
    items = db.query(Conversation).order_by(desc(Conversation.created_at)).all()
    return ConversationListResponse(items=[_conv_to_response(c) for c in items], total=len(items))


@router.post("", response_model=ConversationResponse, status_code=201)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)) -> ConversationResponse:
    c = Conversation(
        id=str(uuid.uuid4()),
        title=(payload.title or "新对话").strip() or "新对话",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _conv_to_response(c)


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationResponse:
    c = db.get(Conversation, conversation_id)
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "对话不存在"})
    return _conv_to_response(c)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    c = db.get(Conversation, conversation_id)
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "对话不存在"})
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": "标题不能为空"})
    c.title = title
    c.updated_at = _now()
    db.commit()
    db.refresh(c)
    return _conv_to_response(c)


@router.delete("/{conversation_id}", response_model=MessageResponse)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> MessageResponse:
    c = db.get(Conversation, conversation_id)
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "对话不存在"})
    # 保留任务：仅解除与对话的绑定，不删除任务记录与资产
    db.query(Task).filter(Task.conversation_id == conversation_id).update(
        {Task.conversation_id: None}, synchronize_session=False
    )
    db.delete(c)
    db.commit()
    return MessageResponse(message=f"对话 {conversation_id} 已删除", detail={"kept_tasks": True})


@router.get("/{conversation_id}/messages", response_model=TaskListResponse)
def list_conversation_messages(conversation_id: str, db: Session = Depends(get_db)) -> TaskListResponse:
    c = db.get(Conversation, conversation_id)
    if not c:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "对话不存在"})
    tasks = (
        db.query(Task)
        .filter(Task.conversation_id == conversation_id)
        .order_by(Task.created_at)
        .all()
    )
    aid_map = _asset_id_map(db, [t.id for t in tasks])
    return TaskListResponse(
        items=[_to_response(t, aid_map.get(t.id)) for t in tasks],
        total=len(tasks),
        page=1,
        page_size=len(tasks),
    )
