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

"""可灵 Kling 4.0 主体 / 音色管理路由。

通过已配置的 kling provider 凭据代理到可灵新版 API，让全能参考里用到的
element_id / voice_id 可以在本应用内创建与查询。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApiProvider
from ..providers import ProviderError, get_provider
from ..providers.kling_provider import KlingProvider
from ..utils.crypto import decrypt

router = APIRouter(prefix="/kling", tags=["kling"])


class ElementCreate(BaseModel):
    name: str = Field(..., max_length=20, description="主体名称")
    description: str = Field(..., max_length=100, description="主体描述")
    reference_type: str = Field(..., pattern="^(image_refer|video_refer)$")
    frontal_image_url: str | None = None
    refer_image_urls: list[str] = Field(default_factory=list)
    refer_video_url: str | None = None
    element_voice_id: str | None = None
    tag_ids: list[str] = Field(default_factory=list)


class VoiceCreate(BaseModel):
    name: str = Field(..., max_length=20, description="音色名称")
    voice_url: str | None = None
    video_id: str | None = None


class IdRequest(BaseModel):
    id: str = Field(..., description="主体 ID 或音色 ID")


def _get_kling_provider(db: Session) -> KlingProvider:
    row = (
        db.query(ApiProvider)
        .filter(ApiProvider.slug == "kling")
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="未配置可灵 Provider（slug=kling）")
    try:
        api_key = decrypt(row.api_key_enc) if row.api_key_enc else ""
    except Exception:
        api_key = ""
    provider = get_provider("kling", base_url=row.base_url, api_key=api_key,
                            config=json.loads(row.config_json or "{}"))
    if not isinstance(provider, KlingProvider):
        raise HTTPException(status_code=500, detail="slug=kling 未解析到 KlingProvider")
    return provider


def _run(coro):  # type: ignore[no-untyped-def]
    try:
        return asyncio.run(coro)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/elements")
def list_elements(page_num: int = 1, page_size: int = 30, db: Session = Depends(get_db)):
    return {"items": _run(_get_kling_provider(db).list_elements(page_num, page_size))}


@router.post("/elements", status_code=201)
def create_element(payload: ElementCreate, db: Session = Depends(get_db)):
    task_id = _run(_get_kling_provider(db).create_element(
        element_name=payload.name,
        element_description=payload.description,
        reference_type=payload.reference_type,
        frontal_image_url=payload.frontal_image_url,
        refer_image_urls=payload.refer_image_urls,
        refer_video_url=payload.refer_video_url,
        element_voice_id=payload.element_voice_id,
        tag_ids=payload.tag_ids,
    ))
    return {"task_id": task_id}


@router.get("/elements/{task_id}")
def get_element(task_id: str, db: Session = Depends(get_db)):
    return _run(_get_kling_provider(db).get_element(task_id))


@router.post("/elements/delete")
def delete_element(payload: IdRequest, db: Session = Depends(get_db)):
    return _run(_get_kling_provider(db).delete_element(payload.id))


@router.get("/voices")
def list_voices(page_num: int = 1, page_size: int = 30, db: Session = Depends(get_db)):
    return {"items": _run(_get_kling_provider(db).list_voices(page_num, page_size))}


@router.post("/voices", status_code=201)
def create_voice(payload: VoiceCreate, db: Session = Depends(get_db)):
    task_id = _run(_get_kling_provider(db).create_voice(
        voice_name=payload.name, voice_url=payload.voice_url, video_id=payload.video_id,
    ))
    return {"task_id": task_id}


@router.get("/voices/{task_id}")
def get_voice(task_id: str, db: Session = Depends(get_db)):
    return _run(_get_kling_provider(db).get_voice(task_id))


@router.post("/voices/delete")
def delete_voice(payload: IdRequest, db: Session = Depends(get_db)):
    return _run(_get_kling_provider(db).delete_voice(payload.id))
