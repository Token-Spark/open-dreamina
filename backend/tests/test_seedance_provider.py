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

"""直连火山方舟 SeedanceProvider 测试：模型 ID、2.5 新参数门禁、样片两步流程与全模态参考 content 结构。

不发起真实网络请求：仅测试纯函数（_build_params / _build_multimodal_content）与
_generate 在 draft_task_id 分支下的 payload 组装（monkeypatch _create_task/_poll_task/_download_video）。
"""
from __future__ import annotations

import asyncio

from app.providers.seedance_provider import (
    MODEL_SEEDANCE_2_5,
    SeedanceProvider,
    _build_draft_task_content,
    _is_seedance25,
)


def _provider() -> SeedanceProvider:
    return SeedanceProvider(api_key="test-key")


def test_model_id_is_canonical():
    assert MODEL_SEEDANCE_2_5 == "doubao-seedance-2-5-260628"
    assert _is_seedance25(MODEL_SEEDANCE_2_5)
    assert _is_seedance25("doubao_seedance_2_5")
    assert _is_seedance25("seedance2.5")
    assert not _is_seedance25("doubao-seedance-2-0-260128")


def test_build_params_seed_gated_for_25():
    p = _provider()
    # 2.5 不支持 seed：即使传入也不下发
    params = p._build_params(
        {"seed": 42, "width": 1248, "height": 704, "duration": 8}, MODEL_SEEDANCE_2_5
    )
    assert "seed" not in params
    assert params["resolution"] == "720p"
    assert params["ratio"] == "16:9"
    assert params["duration"] == 8


def test_build_params_draft_forces_480p():
    p = _provider()
    params = p._build_params(
        {"draft": True, "width": 1248, "height": 704, "duration": 5}, MODEL_SEEDANCE_2_5
    )
    assert params["draft"] is True
    assert params["resolution"] == "480p"


def test_build_params_25_new_fields():
    p = _provider()
    params = p._build_params(
        {
            "generate_audio": False,
            "omni_reference_task_type": "extend",
            "output_format": "mov",
            "resolution": "2160p",  # 前端 4K 档位 -> API 4k
        },
        MODEL_SEEDANCE_2_5,
    )
    assert params["generate_audio"] is False
    assert params["omni_reference_task_type"] == "extend"
    assert params["output_format"] == "mov"
    assert params["resolution"] == "4k"
    # extend 强制 adaptive
    assert params["ratio"] == "adaptive"


def test_build_params_edit_forces_duration_minus_one():
    p = _provider()
    params = p._build_params(
        {"omni_reference_task_type": "edit", "duration": 8}, MODEL_SEEDANCE_2_5
    )
    assert params["duration"] == -1
    assert params["ratio"] == "adaptive"


def test_build_params_20_ignores_25_only_fields():
    p = _provider()
    params = p._build_params(
        {
            "draft": True,
            "omni_reference_task_type": "reference",
            "output_format": "mov",
            "generate_audio": True,
        },
        "doubao-seedance-2-0-260128",
    )
    assert "draft" not in params
    assert "omni_reference_task_type" not in params
    assert "output_format" not in params
    assert params["generate_audio"] is True


def test_build_multimodal_content_structure():
    p = _provider()
    kwargs = {
        "reference_image_bytes_list": [b"\x89PNG\r\nfake-image"],
        "reference_video_urls": ["https://example.com/v.mp4"],
        "reference_audio_bytes_list": [b"RIFF____WAVEfake-audio"],
    }
    content = p._build_multimodal_content(b"", kwargs, MODEL_SEEDANCE_2_5)
    kinds = [(c["type"], c.get("role")) for c in content]
    assert ("image_url", "reference_image") in kinds
    assert ("video_url", "reference_video") in kinds
    assert ("audio_url", "reference_audio") in kinds
    # 自动声明 reference，避免 auto 异步报错
    assert kwargs["omni_reference_task_type"] == "reference"
    # 图片走 base64 data URL，视频保留公网 URL，音频走 base64 data URL
    image = next(c for c in content if c["type"] == "image_url")
    video = next(c for c in content if c["type"] == "video_url")
    audio = next(c for c in content if c["type"] == "audio_url")
    assert image["image_url"]["url"].startswith("data:image/png;base64,")
    assert video["video_url"]["url"] == "https://example.com/v.mp4"
    assert audio["audio_url"]["url"].startswith("data:audio/wav;base64,")


def test_draft_task_content_element():
    assert _build_draft_task_content("cgt-2026-test") == {
        "type": "draft_task",
        "draft_task": {"id": "cgt-2026-test"},
    }


def test_generate_from_draft_task_sends_minimal_payload():
    p = _provider()
    captured: dict = {}

    async def fake_create(client, model_id, content, params):
        captured.update(model=model_id, content=content, params=params)
        return "cgt-final-1"

    async def fake_poll(client, task_id):
        return {"status": "succeeded", "content": {"video_url": "https://cdn/x.mp4"}}

    async def fake_download(url):
        return b"fake-video"

    p._create_task = fake_create  # type: ignore[method-assign]
    p._poll_task = fake_poll  # type: ignore[method-assign]
    p._download_video = fake_download  # type: ignore[method-assign]

    result = asyncio.run(
        p.text_to_video(
            "unused prompt", draft_task_id="cgt-draft-1", model_id=MODEL_SEEDANCE_2_5
        )
    )
    assert captured["content"] == [
        {"type": "text", "text": "unused prompt"},
        {"type": "draft_task", "draft_task": {"id": "cgt-draft-1"}},
    ]
    # 基于样片出正式片：params 为空（部分参数禁止重复传入），仅保留 model/content
    assert captured["params"] == {}
    assert result.metadata["draft_task_id"] == "cgt-draft-1"
