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

"""Provider 配置路由：CRUD + test 连通性。"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApiProvider
from ..providers import ProviderError, ProviderFactory, get_provider
from ..schemas import (
    MessageResponse,
    ProviderCreate,
    ProviderResponse,
    ProviderSlugOption,
    ProviderTestBeforeCreate,
    ProviderTestOverride,
    ProviderTestResult,
    ProviderUpdate,
)
from ..utils.crypto import decrypt, encrypt, mask_api_key
from ..worker import dreamina_cli_user_credit_task

router = APIRouter(prefix="/providers", tags=["providers"])

# 即梦 CLI 的连通性测试必须在 worker 节点执行（CLI 装在 worker 所在机器）；
# 拆分后的视频/图片两个 slug 与遗留 slug 共用同一套 CLI 自检
_DREAMINA_CLI_SLUGS = {"dreamina-cli", "dreamina-seedance", "dreamina-seedream"}


def _test_dreamina_cli_on_worker(cli_path: str | None) -> ProviderTestResult:
    """分发 user_credit 自检任务到 worker，同步等待结果。"""
    start = time.perf_counter()
    try:
        result = dreamina_cli_user_credit_task.apply_async(args=[cli_path]).get(timeout=60)
    except CeleryTimeoutError:
        return ProviderTestResult(
            success=False,
            message="celery-worker 不在线，无法检测即梦 CLI，请检查 worker 容器是否运行",
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    except Exception as e:
        return ProviderTestResult(
            success=False,
            message=f"测试异常: {type(e).__name__}: {e}",
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    return ProviderTestResult(
        success=bool(result.get("success")),
        message=result.get("message", ""),
        latency_ms=int((time.perf_counter() - start) * 1000),
    )


def _to_response(p: ApiProvider) -> ProviderResponse:
    try:
        plain = decrypt(p.api_key_enc)
    except Exception:
        plain = ""
    return ProviderResponse(
        id=p.id,
        name=p.name,
        slug=p.slug,
        base_url=p.base_url,
        api_key_masked=mask_api_key(plain),
        is_active=bool(p.is_active),
        config=json.loads(p.config_json or "{}"),
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("", response_model=list[ProviderResponse])
def list_providers(db: Session = Depends(get_db)) -> list[ProviderResponse]:
    items = db.query(ApiProvider).order_by(ApiProvider.created_at).all()
    return [_to_response(p) for p in items]


@router.get("/slug-options", response_model=list[ProviderSlugOption])
def list_slug_options() -> list[ProviderSlugOption]:
    """返回所有可用 slug 及其元信息，供前端「添加自定义服务」下拉选择。

    静态路径置于 /{provider_id} 之前，避免被动态路由捕获。
    """
    return [ProviderSlugOption(**info) for info in ProviderFactory.list_slug_info()]


@router.post("/test-before-create", response_model=ProviderTestResult)
def test_provider_before_create(payload: ProviderTestBeforeCreate) -> ProviderTestResult:
    """新建前连通性测试：无需先落库即可校验 slug / API Key / base_url。"""
    if payload.slug in _DREAMINA_CLI_SLUGS:
        return _test_dreamina_cli_on_worker(payload.base_url)

    try:
        provider = get_provider(
            payload.slug,
            base_url=payload.base_url,
            api_key=payload.api_key,
            config=payload.config,
        )
    except ProviderError as e:
        return ProviderTestResult(success=False, message=str(e))

    start = time.perf_counter()
    try:
        ok = asyncio.run(provider.test_connection())
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderTestResult(
            success=ok,
            message="连通性测试通过" if ok else "连通性测试失败（API Key 无效或网络不通）",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderTestResult(
            success=False,
            message=f"测试异常: {type(e).__name__}: {e}",
            latency_ms=latency_ms,
        )


@router.post("", response_model=ProviderResponse, status_code=201)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db)) -> ProviderResponse:
    existing = db.query(ApiProvider).filter(ApiProvider.slug == payload.slug).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"code": "conflict", "message": f"slug '{payload.slug}' 已存在"},
        )

    p = ApiProvider(
        id=str(uuid.uuid4()),
        name=payload.name,
        slug=payload.slug,
        base_url=payload.base_url,
        api_key_enc=encrypt(payload.api_key),
        is_active=1 if payload.is_active else 0,
        config_json=json.dumps(payload.config, ensure_ascii=False),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_response(p)


@router.put("/{provider_id}", response_model=ProviderResponse)
def update_provider(
    provider_id: str,
    payload: ProviderUpdate,
    db: Session = Depends(get_db),
) -> ProviderResponse:
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Provider 不存在"})

    if payload.name is not None:
        p.name = payload.name
    if payload.base_url is not None:
        p.base_url = payload.base_url
    if payload.api_key is not None:
        p.api_key_enc = encrypt(payload.api_key)
    if payload.is_active is not None:
        p.is_active = 1 if payload.is_active else 0
    if payload.config is not None:
        p.config_json = json.dumps(payload.config, ensure_ascii=False)

    from datetime import datetime
    p.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    db.refresh(p)
    return _to_response(p)


@router.delete("/{provider_id}", response_model=MessageResponse)
def delete_provider(provider_id: str, db: Session = Depends(get_db)) -> MessageResponse:
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Provider 不存在"})
    db.delete(p)
    db.commit()
    return MessageResponse(message=f"Provider {provider_id} 已删除")


@router.post("/{provider_id}/test", response_model=ProviderTestResult)
def test_provider(
    provider_id: str,
    payload: ProviderTestOverride | None = None,
    db: Session = Depends(get_db),
) -> ProviderTestResult:
    p = db.get(ApiProvider, provider_id)
    if not p:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Provider 不存在"})

    # api_key：优先用覆盖值，否则解密已落库的（编辑模式留空 = 保持旧 Key）
    if payload and payload.api_key:
        api_key = payload.api_key
    else:
        try:
            api_key = decrypt(p.api_key_enc)
        except Exception as e:
            return ProviderTestResult(success=False, message=f"API Key 解密失败: {e}")

    base_url = p.base_url
    if payload and payload.base_url:
        base_url = payload.base_url
    config = json.loads(p.config_json or "{}") if not (payload and payload.config is not None) else payload.config

    if p.slug in _DREAMINA_CLI_SLUGS:
        return _test_dreamina_cli_on_worker(base_url)

    try:
        provider = get_provider(p.slug, base_url=base_url, api_key=api_key, config=config)
    except ProviderError as e:
        return ProviderTestResult(success=False, message=str(e))

    start = time.perf_counter()
    try:
        ok = asyncio.run(provider.test_connection())
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderTestResult(
            success=ok,
            message="连通性测试通过" if ok else "连通性测试失败（API Key 无效或网络不通）",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ProviderTestResult(
            success=False,
            message=f"测试异常: {type(e).__name__}: {e}",
            latency_ms=latency_ms,
        )
