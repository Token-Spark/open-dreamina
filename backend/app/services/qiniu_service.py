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

"""七牛云对象存储服务。

为 Spark Hub Seedance 参考素材提供公网临时 URL（默认 14 天自动过期）：
- 上传本地素材到七牛云空间，返回公网访问 URL；
- 对上传对象设置生命周期规则（delete_after_days），到期自动删除，避免长期占用存储。

配置项（.env）：
- QINIU_ACCESS_KEY / QINIU_SECRET_KEY：七牛云密钥
- QINIU_BUCKET：存储空间名称
- QINIU_DOMAIN：空间访问域名（形如 https://xxx.clouddn.com）
- QINIU_AUDIT_EXPIRE_DAYS：临时文件保留天数，默认 14
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from qiniu import Auth, BucketManager, put_file

from ..config import settings
from ..providers import ProviderError


def is_configured() -> bool:
    """七牛云是否已配置（未配置时回退到 public_base_url 方案）。"""
    return bool(
        settings.qiniu_access_key
        and settings.qiniu_secret_key
        and settings.qiniu_bucket
        and settings.qiniu_domain
    )


def _auth() -> Auth:
    if not (settings.qiniu_access_key and settings.qiniu_secret_key):
        raise ProviderError(
            "未配置七牛云存储（QINIU_ACCESS_KEY / QINIU_SECRET_KEY），"
            "无法为 Seedance 参考素材提供公网临时 URL，请在 .env 中配置"
        )
    return Auth(settings.qiniu_access_key, settings.qiniu_secret_key)


def _bucket() -> str:
    if not settings.qiniu_bucket:
        raise ProviderError("未配置七牛云存储空间（QINIU_BUCKET），请在 .env 中配置")
    return settings.qiniu_bucket


def _domain() -> str:
    if not settings.qiniu_domain:
        raise ProviderError("未配置七牛云访问域名（QINIU_DOMAIN），请在 .env 中配置")
    return settings.qiniu_domain.rstrip("/")


def _upload_sync(asset_id: str, file_path: Path, filename: str) -> str:
    """同步上传素材到七牛云并设置生命周期，返回公网 URL。"""
    auth = _auth()
    bucket = _bucket()
    key = f"audit/{asset_id}/{filename}"
    token = auth.upload_token(bucket, key)
    ret, info = put_file(token, key, str(file_path))
    if info.status_code != 200:
        raise ProviderError(
            f"七牛云上传失败（HTTP {info.status_code}）：{info.error or ret}"
        )
    # 设置对象生命周期：到期自动删除（临时文件）。失败不阻断上传，仅不会自动过期。
    try:
        bm = BucketManager(auth)
        _, lc_info = bm.set_object_lifecycle(
            bucket, key, delete_after_days=settings.qiniu_audit_expire_days
        )
        if lc_info.status_code not in (200, 201):
            pass
    except Exception:
        pass
    return f"{_domain()}/{key}"


async def upload_asset_to_qiniu(asset_id: str, file_path: Path, filename: str) -> str:
    """上传素材到七牛云并设置生命周期，返回公网 URL（异步包装，避免阻塞事件循环）。"""
    return await asyncio.to_thread(_upload_sync, asset_id, file_path, filename)
