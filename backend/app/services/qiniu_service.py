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

from qiniu import Auth, BucketManager, put_data, put_file

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


# ---------------- 团队资产同步（创作资产素材库共享） ----------------
# key 结构：team-assets/{tag}/{owner_id}/{asset_id}/{filename}
# 每个资产独立 key 且按 owner 分目录，天然互不覆盖；拉取时按前缀列举。
# 与 audit 临时文件不同，团队资产长期保留，不设置生命周期。

TEAM_SYNC_KEY_PREFIX = "team-assets"
_MANIFEST_NAME = "manifest.json"


def build_team_key(tag: str, owner_id: str, asset_id: str, filename: str) -> str:
    """构造团队资产对象 key。tag/owner_id/asset_id 需为安全字符（不含 /）。"""
    return f"{TEAM_SYNC_KEY_PREFIX}/{tag}/{owner_id}/{asset_id}/{filename}"


def public_url(key: str) -> str:
    """拼接对象的公网访问 URL。"""
    from urllib.parse import quote

    return f"{_domain()}/{quote(key)}"


def upload_team_object(key: str, data: bytes) -> str:
    """上传字节内容到指定 key（团队资产，无生命周期），返回公网 URL。"""
    auth = _auth()
    token = auth.upload_token(_bucket(), key)
    ret, info = put_data(token, key, data)
    if info.status_code != 200:
        raise ProviderError(f"七牛云上传失败（HTTP {info.status_code}）：{info.error or ret}")
    return public_url(key)


def _list_prefix(prefix: str) -> list[str]:
    """列举任意前缀下全部对象 key（自动翻页）。"""
    auth = _auth()
    bucket = _bucket()
    keys: list[str] = []
    marker = None
    while True:
        # qiniu SDK 的 list 返回 (ret, end, info) 三元组
        ret, _end, info = BucketManager(auth).list(bucket, prefix, marker=marker, limit=100)
        if info.status_code != 200:
            raise ProviderError(f"七牛云列举对象失败（HTTP {info.status_code}）：{info.error}")
        for item in ret.get("items", []):
            keys.append(item["key"])
        marker = ret.get("marker") or None
        if not marker:
            return keys


def list_team_keys(tag: str) -> list[str]:
    """列举某标签（项目）目录下全部对象 key。"""
    return _list_prefix(f"{TEAM_SYNC_KEY_PREFIX}/{tag}/")


def list_all_team_keys() -> list[str]:
    """列举团队资产根目录下全部对象 key（项目列表用）。"""
    return _list_prefix(f"{TEAM_SYNC_KEY_PREFIX}/")


def download_team_object(key: str) -> bytes:
    """经公开域名下载对象内容。"""
    import httpx

    url = public_url(key)
    resp = httpx.get(url, timeout=120, follow_redirects=True)
    if resp.status_code != 200:
        raise ProviderError(f"七牛云下载失败（HTTP {resp.status_code}）：{url}")
    return resp.content


def try_download_team_object(key: str) -> bytes | None:
    """下载对象内容；对象不存在时返回 None（供 CAS 读云端版本）。"""
    import httpx

    try:
        return download_team_object(key)
    except ProviderError:
        return None


def manifest_key(tag: str, owner_id: str, asset_id: str) -> str:
    """资产最新清单对象的固定 key（历史版本为 manifest.{version}.json）。"""
    return build_team_key(tag, owner_id, asset_id, _MANIFEST_NAME)


def versioned_manifest_key(tag: str, owner_id: str, asset_id: str, version: int) -> str:
    """资产历史版本清单 key（append-only，构成版本链与审计 trail）。"""
    return build_team_key(tag, owner_id, asset_id, f"manifest.{version}.json")


def project_key(tag: str) -> str:
    """项目元数据对象 key（team-assets/{tag}/project.json）。"""
    return f"{TEAM_SYNC_KEY_PREFIX}/{tag}/project.json"
