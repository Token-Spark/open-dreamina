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

"""Mock Provider - 关键测试组件。

不调用任何外部 API，用 Pillow 绘制带 prompt 文字的占位图片。
支持全部 4 种生成类型（视频/图生视频也返回 PNG 占位图，便于无 Key 测试）。
"""
from __future__ import annotations

import asyncio
from typing import Any

from ..utils.file_utils import render_placeholder_image
from .base import BaseProvider, GenerationResult


def _estimate_mock_tokens(prompt: str, width: int, height: int, steps: int = 30) -> int:
    """为 mock 生成估算一个 token 用量，便于任务中心展示与联调。

    估算口径：prompt 词数 + 像素规模 + 采样步数。仅用于占位，不代表真实消耗。
    """
    prompt_tokens = max(1, len(prompt.split())) if prompt else 1
    pixels = (width * height) // 1024  # 以 1024px² 为 1 单位
    return int(prompt_tokens * 8 + pixels * 4 + steps)


class MockProvider(BaseProvider):
    """Mock Provider：无外部依赖，生成占位图用于联调测试。"""

    SUPPORTED_TYPES = ["text2img", "img2img", "text2video", "img2video"]

    def __init__(
        self,
        base_url: str = "mock://local",
        api_key: str = "mock-key",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.config = config or {}

    async def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        **kwargs: Any,
    ) -> GenerationResult:
        await asyncio.sleep(0.2)
        img_bytes = render_placeholder_image(
            prompt=prompt or "(empty)",
            width=width,
            height=height,
        )
        return GenerationResult(
            file_bytes=img_bytes,
            mime_type="image/png",
            metadata={
                "provider": "mock",
                "model": kwargs.get("model_id", "mock-1"),
                "width": width,
                "height": height,
                "tokens_used": _estimate_mock_tokens(prompt, width, height, steps),
            },
        )

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        await asyncio.sleep(0.2)
        width = int(kwargs.get("width", 1024))
        height = int(kwargs.get("height", 1024))
        steps = int(kwargs.get("steps", 30))
        img_bytes = render_placeholder_image(
            prompt=f"[img2img] {prompt or '(empty)'}",
            width=width,
            height=height,
        )
        return GenerationResult(
            file_bytes=img_bytes,
            mime_type="image/png",
            metadata={
                "provider": "mock",
                "model": kwargs.get("model_id", "mock-1"),
                "mode": "img2img",
                "strength": strength,
                "width": width,
                "height": height,
                "tokens_used": _estimate_mock_tokens(prompt, width, height, steps),
            },
        )

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        await asyncio.sleep(0.2)
        # 视频以占位 PNG 返回，便于无 ffmpeg 编码环境下也能完整跑通流程
        width = 1280
        height = 720
        img_bytes = render_placeholder_image(
            prompt=f"[text2video] {prompt or '(empty)'}",
            width=width,
            height=height,
        )
        return GenerationResult(
            file_bytes=img_bytes,
            mime_type="image/png",
            metadata={
                "provider": "mock",
                "model": kwargs.get("model_id", "mock-video-1"),
                "mode": "text2video",
                "duration": duration,
                "width": width,
                "height": height,
                "tokens_used": _estimate_mock_tokens(prompt, width, height, steps=30) * duration,
            },
        )

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        await asyncio.sleep(0.2)
        width = 1280
        height = 720
        img_bytes = render_placeholder_image(
            prompt=f"[img2video] {prompt or '(empty)'}",
            width=width,
            height=height,
        )
        return GenerationResult(
            file_bytes=img_bytes,
            mime_type="image/png",
            metadata={
                "provider": "mock",
                "model": kwargs.get("model_id", "mock-video-1"),
                "mode": "img2video",
                "duration": duration,
                "width": width,
                "height": height,
                "tokens_used": _estimate_mock_tokens(prompt, width, height, steps=30) * duration,
            },
        )

    async def test_connection(self) -> bool:
        await asyncio.sleep(0.05)
        return True
