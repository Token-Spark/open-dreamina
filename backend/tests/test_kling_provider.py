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

"""Kling 4.0 Provider 测试：新版鉴权域名、版本 path、全能参考 content 结构与门禁。

不发起真实网络请求：测试纯函数（_build_settings / contents 构造 / _rewrite_mentions）
与 _api 业务码校验（monkeypatch _request_with_retry）。
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from app.providers.base import ProviderError
from app.providers.kling_provider import (
    KLING_DEFAULT_BASE_URL,
    MODEL_KLING_4_0,
    MODEL_KLING_4_0_FLASH,
    KlingProvider,
    _normalize_model,
    _ratio_from_size,
)


def _provider() -> KlingProvider:
    return KlingProvider(api_key="k")


def test_default_domain_and_jwt_not_used():
    p = _provider()
    assert p.base_url == KLING_DEFAULT_BASE_URL == "https://api-beijing.klingai.com"
    assert p._headers()["Authorization"] == "Bearer k"


def test_legacy_domain_rewritten():
    p = KlingProvider(base_url="https://api.klingai.com", api_key="k")
    assert p.base_url == KLING_DEFAULT_BASE_URL


def test_model_normalization():
    assert _normalize_model("kling-4.0") == MODEL_KLING_4_0
    assert _normalize_model("kling-4.0-flash") == MODEL_KLING_4_0_FLASH
    assert _normalize_model("kling_4_0_flash") == MODEL_KLING_4_0_FLASH
    assert _normalize_model(None) == MODEL_KLING_4_0


def test_build_settings_4_0():
    s = KlingProvider._build_settings(
        {"resolution": "1080p", "aspect_ratio": "16:9", "duration": 8},
        MODEL_KLING_4_0, omni=False,
    )
    assert s == {"resolution": "1080p", "aspect_ratio": "16:9", "duration": 8}


def test_build_settings_flash_clamps_resolution_duration():
    s = KlingProvider._build_settings(
        {"resolution": "2160p", "aspect_ratio": "auto", "duration": 30},
        MODEL_KLING_4_0_FLASH, omni=True,
    )
    assert s["resolution"] == "720p"
    assert "duration" not in s  # 30s 超出 Flash 上限 20s，省略由模型决定
    assert s["aspect_ratio"] == "adaptive"
    assert s["audio"] == "native"


def test_build_settings_ratio_from_size():
    assert _ratio_from_size(1280, 720) == "16:9"
    assert _ratio_from_size(720, 1280) == "9:16"
    s = KlingProvider._build_settings({"width": 720, "height": 1280}, MODEL_KLING_4_0, omni=False)
    assert s["aspect_ratio"] == "9:16"


def test_ratio_adaptive_not_allowed_for_t2v():
    s = KlingProvider._build_settings({"aspect_ratio": "auto"}, MODEL_KLING_4_0, omni=False)
    assert s["aspect_ratio"] == "16:9"


def test_rewrite_mentions():
    p = _provider()
    refs = [{"id": "image_1"}, {"id": "video_1"}]
    assert p._rewrite_mentions("参考 @{角色} 与 @{动作}", refs) == "参考 @image_1 与 @video_1"
    # token 多于素材时多余的被移除
    assert p._rewrite_mentions("@{a} @{b} @{c}", refs) == "@image_1 @video_1 "


def test_omni_contents_structure_and_caps():
    p = _provider()
    kwargs = {
        "reference_image_bytes_list": [b"\x89PNG\r\nfake"],
        "reference_video_urls": ["https://example.com/v.mp4"],
        "element_ids": ["el-1"],
        "voice_ids": ["vo-1"],
    }
    contents = p._build_omni_contents("参考 @{角色}", b"\x89PNG\r\nfake", kwargs, MODEL_KLING_4_0)
    types = [c["type"] for c in contents]
    assert types[0] == "prompt"
    assert "first_frame" in types
    assert "refer_image" not in types  # 主图与列表首图相同，已去重
    assert "feature_video" in types
    assert "element" in types
    assert "voice" in types
    prompt = contents[0]["text"]
    assert "@image" in prompt


def test_flash_rejects_voice_reference():
    p = _provider()
    kwargs = {"voice_ids": ["vo-1"]}
    contents = p._build_omni_contents("hi", b"", kwargs, MODEL_KLING_4_0_FLASH)
    assert not any(c["type"] == "voice" for c in contents)


def test_multi_keyframe_constraints():
    p = _provider()
    kwargs = {
        "frame_mode": "first_last",
        "last_image_bytes": b"\xff\xd8\xfflast",
        "middle_image_bytes_list": [b"\xff\xd8\xffmid"],
    }
    contents = p._build_image_to_video_contents("go", b"\xff\xd8\xfffirst", kwargs, MODEL_KLING_4_0)
    types = [c["type"] for c in contents]
    assert types == ["prompt", "first_frame", "middle_frame", "last_frame"]
    # Flash 不支持多关键帧
    kwargs2 = dict(kwargs)
    contents2 = p._build_image_to_video_contents("go", b"\xff\xd8\xfffirst", kwargs2, MODEL_KLING_4_0_FLASH)
    assert "middle_frame" not in [c["type"] for c in contents2]


def test_first_last_requires_tail():
    p = _provider()
    try:
        p._build_image_to_video_contents("go", b"img", {"frame_mode": "first_last"}, MODEL_KLING_4_0)
        raise AssertionError("expected ProviderError")
    except ProviderError:
        pass


def test_api_business_code_check():
    p = _provider()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"code": 400, "message": "bad", "data": {}}
    resp.text = '{"code":400}'

    async def fake_request(*args, **kwargs):
        return resp

    p._request_with_retry = fake_request  # type: ignore[method-assign]
    try:
        asyncio.run(p._api(get_async_client_stub(), "POST", "/x", json={}))
        raise AssertionError("expected ProviderError")
    except ProviderError as exc:
        assert "400" in str(exc)


def get_async_client_stub():
    return MagicMock()
