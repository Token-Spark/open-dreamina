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

"""参考素材提审的类型映射回归测试。

背景：提审接口（Spark Hub seedance_asset_audit）只处理 Image / Video 两类素材，
音频不在提审范围内（强行提交会被上游以 asset_api_http_400 拒绝）。
此处锁定三条不变量：

1. 映射表：image -> Image、video -> Video，未登记类型必须快速失败；
2. 音频提审直接 400（且发生在 provider 解析之前，不触发任何上游请求）；
3. 图片提审携带 AssetType=Image（防止映射表退化成布尔判断）。
"""
from __future__ import annotations

import uuid

import pytest

from app.models import Asset
from app.providers import ProviderError
from app.services import asset_audit_service
from app.services.asset_audit_service import _resolve_audit_asset_type

API = "/api/v1/assets"
PROVIDER_SLUG = "sparkhub-seedance"
# 以 ID3 魔术字节开头的伪音频负载，足以让 MIME 探测判定为 audio/mpeg
_AUDIO_BYTES = b"ID3\x03\x00\x00\x00" + b"\x00" * 32


def _upload(client, filename: str, content_type: str, data: bytes) -> dict:
    resp = client.post(f"{API}/upload", files={"file": (filename, data, content_type)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _audio_asset(client) -> dict:
    return _upload(client, f"{uuid.uuid4().hex}.mp3", "audio/mpeg", _AUDIO_BYTES)


# ---------------- 类型映射表（单元） ----------------


@pytest.mark.parametrize(
    ("asset_type", "expected"),
    [("image", "Image"), ("video", "Video"), ("IMAGE", "Image"), ("Video", "Video")],
)
def test_resolve_audit_asset_type_maps_supported_types(asset_type: str, expected: str):
    asset = Asset(id="asset-1", type=asset_type, file_path="images/x.png")
    assert _resolve_audit_asset_type(asset) == expected


def test_resolve_audit_asset_type_rejects_audio():
    asset = Asset(id="asset-audio", type="audio", file_path="audio/x.mp3")
    with pytest.raises(ProviderError) as exc:
        _resolve_audit_asset_type(asset)
    message = str(exc.value)
    assert "不在提审范围内" in message
    assert "audio" in message


# ---------------- 接口行为（端到端） ----------------


def test_audio_upload_is_typed_as_audio(client):
    """音频文件上传后素材类型必须是 audio（提审分流的输入前提）。"""
    assert _audio_asset(client)["type"] == "audio"


def test_audio_asset_audit_rejected_before_provider_lookup(client, monkeypatch):
    """音频提审必须快速失败：400 + 可读原因。

    未配置 provider 也能得到类型错误，说明类型校验先于 provider 解析与公网 URL 生成，
    不会为注定失败的请求产生任何副作用。
    """
    asset = _audio_asset(client)

    def _forbidden_provider(_db, _slug):
        raise AssertionError("类型校验应早于 provider 解析")

    async def _forbidden_url(_asset):
        raise AssertionError("音频不应生成公网 URL")

    monkeypatch.setattr(asset_audit_service, "_load_sparkhub_provider", _forbidden_provider)
    monkeypatch.setattr(asset_audit_service, "asset_public_url", _forbidden_url)

    resp = client.post(f"{API}/{asset['id']}/audit", json={"provider": PROVIDER_SLUG})
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "audit_failed"
    assert "不在提审范围内" in detail["message"]


def test_image_asset_audit_submits_image_asset_type(client, png_bytes, monkeypatch):
    """图片提审必须向提审接口发送 AssetType=Image。"""
    asset = _upload(client, f"{uuid.uuid4().hex}.png", "image/png", png_bytes)
    captured: dict = {}

    class _FakeProvider:
        base_url = "https://sparkhub.example.com"
        api_key = "test-key"

    async def _fake_public_url(_asset):
        return "https://cdn.example.com/ref.png"

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "code": 200,
                "data": {"asset_id": "up-1", "asset_url": "asset://up-1", "status": "pending"},
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["payload"] = json
            return _FakeResponse()

    monkeypatch.setattr(asset_audit_service, "_load_sparkhub_provider", lambda _db, _slug: _FakeProvider())
    monkeypatch.setattr(asset_audit_service, "asset_public_url", _fake_public_url)
    monkeypatch.setattr(asset_audit_service.httpx, "AsyncClient", _FakeAsyncClient)

    resp = client.post(f"{API}/{asset['id']}/audit", json={"provider": PROVIDER_SLUG})
    assert resp.status_code == 200, resp.text
    assert captured["url"].endswith("/task/seedance_asset_audit/submit")
    assert captured["payload"] == {"url": "https://cdn.example.com/ref.png", "AssetType": "Image"}
    assert resp.json()["audit_status"] == "pending"
