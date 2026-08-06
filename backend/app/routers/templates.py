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

"""Prompt 模板路由：CRUD。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PromptTemplate
from ..schemas import (
    MessageResponse,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)

router = APIRouter(prefix="/templates", tags=["templates"])


def _to_response(t: PromptTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=t.id,
        name=t.name,
        category=t.category,
        prompt_text=t.prompt_text,
        negative_prompt=t.negative_prompt,
        params=json.loads(t.params_json or "{}"),
        preview_path=t.preview_path,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("", response_model=list[TemplateResponse])
def list_templates(
    category: str | None = None,
    db: Session = Depends(get_db),
) -> list[TemplateResponse]:
    query = db.query(PromptTemplate)
    if category:
        query = query.filter(PromptTemplate.category == category)
    items = query.order_by(PromptTemplate.created_at.desc()).all()
    return [_to_response(t) for t in items]


@router.post("", response_model=TemplateResponse, status_code=201)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db)) -> TemplateResponse:
    t = PromptTemplate(
        id=str(uuid.uuid4()),
        name=payload.name,
        category=payload.category,
        prompt_text=payload.prompt_text,
        negative_prompt=payload.negative_prompt,
        params_json=json.dumps(payload.params, ensure_ascii=False),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_response(t)


@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: str,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
) -> TemplateResponse:
    t = db.get(PromptTemplate, template_id)
    if not t:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "模板不存在"})

    if payload.name is not None:
        t.name = payload.name
    if payload.category is not None:
        t.category = payload.category
    if payload.prompt_text is not None:
        t.prompt_text = payload.prompt_text
    if payload.negative_prompt is not None:
        t.negative_prompt = payload.negative_prompt
    if payload.params is not None:
        t.params_json = json.dumps(payload.params, ensure_ascii=False)

    t.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    db.refresh(t)
    return _to_response(t)


@router.delete("/{template_id}", response_model=MessageResponse)
def delete_template(template_id: str, db: Session = Depends(get_db)) -> MessageResponse:
    t = db.get(PromptTemplate, template_id)
    if not t:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "模板不存在"})
    db.delete(t)
    db.commit()
    return MessageResponse(message=f"模板 {template_id} 已删除")
