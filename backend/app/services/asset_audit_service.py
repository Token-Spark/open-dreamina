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

"""Seedance 参考素材审核服务（Spark Hub seedance_asset_audit）。

对接 Spark Hub 中转站的素材提审接口（见 .trae/docs/spark-hub router.md 第 7 节）：
- POST /task/seedance_asset_audit/submit  提交素材，返回 asset_id（status=pending）
- POST /task/seedance_asset_audit/status  查询审核状态（pending/active/failed）

审核通过（active）后返回 asset:// 地址，用于创建视频任务时的 image_urls/video_urls。
真人、虚拟人像等受限参考素材必须提审通过后才能用于视频生成。
"""
from __future__ import annotations

import json

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ApiProvider, Asset
from ..providers import ProviderError
from ..utils.crypto import decrypt

_SUBMIT_PATH = "/task/seedance_asset_audit/submit"
_STATUS_PATH = "/task/seedance_asset_audit/status"


def _load_sparkhub_provider(db: Session, provider_slug: str):
    """按 slug 加载 Spark Hub Provider（复用 worker 的加载逻辑）。"""
    from ..providers import get_provider

    provider_row = (
        db.query(ApiProvider)
        .filter((ApiProvider.slug == provider_slug) | (ApiProvider.id == provider_slug))
        .first()
    )
    if not provider_row:
        raise ProviderError(f"Provider {provider_slug} 未配置，无法提交素材审核")
    try:
        api_key = decrypt(provider_row.api_key_enc)
    except Exception:
        api_key = ""
    config = json.loads(provider_row.config_json or "{}")
    return get_provider(
        provider_row.slug,
        base_url=provider_row.base_url,
        api_key=api_key,
        config=config,
    )


def _asset_public_url(asset: Asset) -> str:
    """构造素材的公网访问 URL（供 Spark Hub 拉取审核）。"""
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        raise ProviderError(
            "未配置 public_base_url，无法提交素材审核。"
            "请在 .env 中配置外部可访问的服务地址（形如 https://your-host）"
        )
    return f"{base}/api/v1/assets/{asset.id}/file"


def _raise_business_error(data: dict, context: str) -> None:
    """解析 Spark Hub 业务码，非 200 时抛出带提示的错误。"""
    code = data.get("code")
    if code in (None, 200):
        return
    message = data.get("error") or data.get("message") or ""
    raise ProviderError(f"{context}失败（code={code}）：{message}".strip())


async def submit_asset_audit(db: Session, asset: Asset, provider_slug: str) -> Asset:
    """提交素材审核，返回更新后的 asset（status=pending）。"""
    provider = _load_sparkhub_provider(db, provider_slug)
    url = _asset_public_url(asset)
    asset_type = "Video" if asset.type == "video" else "Image"
    payload = {"url": url, "AssetType": asset_type}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{provider.base_url}{_SUBMIT_PATH}",
            headers={"X-API-Key": provider.api_key, "Content-Type": "application/json"},
            json=payload,
        )
        data = resp.json()
    _raise_business_error(data, "素材提审")
    d = data.get("data") or {}
    asset.audit_asset_id = d.get("asset_id")
    asset.audit_asset_url = d.get("asset_url")
    asset.audit_status = d.get("status") or "pending"
    asset.audit_error = None
    db.commit()
    db.refresh(asset)
    return asset


async def check_asset_audit(db: Session, asset: Asset, provider_slug: str) -> Asset:
    """查询素材审核状态，更新 asset 并返回。"""
    if not asset.audit_asset_id:
        raise ProviderError("素材尚未提交审核，请先调用提审接口")
    provider = _load_sparkhub_provider(db, provider_slug)
    payload = {"asset_id": asset.audit_asset_id}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{provider.base_url}{_STATUS_PATH}",
            headers={"X-API-Key": provider.api_key, "Content-Type": "application/json"},
            json=payload,
        )
        data = resp.json()
    _raise_business_error(data, "查询审核状态")
    d = data.get("data") or {}
    asset.audit_status = d.get("status") or asset.audit_status
    if d.get("asset_url"):
        asset.audit_asset_url = d.get("asset_url")
    if d.get("error"):
        asset.audit_error = str(d.get("error"))
    db.commit()
    db.refresh(asset)
    return asset
