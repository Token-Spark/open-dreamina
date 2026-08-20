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

"""Spark Hub Seedream 生图 Provider。

对接 Spark Hub 中转站的 Seedream 文生图模型（api_name：doubao_seedream_5 等）。
异步任务模式，返回 result.images[]（图片 URL 数组）。
"""
from __future__ import annotations

from typing import Any

from .base import GenerationResult, ProviderError
from .sparkhub_base import SparkHubBaseProvider, _find


def _aspect_ratio_from_size(width: int, height: int) -> str:
    """按宽高比就近归入 Spark Hub 支持的比例串（数据驱动查找）。"""
    if width <= 0 or height <= 0:
        return "9:16"  # Spark Hub 默认比例
    ratio = width / height
    # (比例值, 比例串)，越靠前优先级越高
    candidates = [
        (21 / 9, "21:9"),
        (16 / 9, "16:9"),
        (3 / 2, "3:2"),
        (4 / 3, "4:3"),
        (1 / 1, "1:1"),
        (3 / 4, "3:4"),
        (2 / 3, "2:3"),
        (9 / 16, "9:16"),
    ]
    return min(candidates, key=lambda c: abs(ratio - c[0]))[1]


class SparkHubSeedreamProvider(SparkHubBaseProvider):
    SUPPORTED_TYPES = ["text2img", "img2img"]

    def _build_create_payload(self, prompt: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        api_name = kwargs.get("model_id") or self.config.get("model_id")
        if not api_name:
            raise ProviderError("Spark Hub Seedream 未配置 api_name（模型 ID）")
        width = int(kwargs.get("width") or 0)
        height = int(kwargs.get("height") or 0)
        pl: dict[str, Any] = {
            "api_name": api_name,
            "prompt": prompt,
            "aspect_ratio": _aspect_ratio_from_size(width, height),
            "resolution": "1440p",
        }
        # 火山方舟 size 参数有两种互斥方式：
        #   方式 1：分辨率档位（"2K"/"3K"/"4K"），由模型根据 prompt 判断宽高比
        #   方式 2：明确像素值（"1728x2304"），确定性输出
        # 当有明确 width/height 时必须用方式 2，否则方式 1 会让模型自行判断宽高比，
        # 导致 aspect_ratio 参数被忽略（如 3:4 输出成正方形）。
        if width > 0 and height > 0:
            size = f"{width}x{height}"
        else:
            size = kwargs.get("size") or kwargs.get("resolution")
        if size:
            pl["kwargs"] = {"size": str(size)}
        # 多图生成数量（上游支持时生效；Pro 模型仅单图，忽略该参数）
        count = int(kwargs.get("count") or 1)
        if count > 1:
            pl.setdefault("kwargs", {})["count"] = count
        return pl

    def _extract_result_urls(self, polled: dict[str, Any]) -> list[str]:
        images = _find(polled, "images", "result")
        if isinstance(images, dict):
            images = images.get("images")
        if not isinstance(images, list):
            return []
        return [u for u in images if isinstance(u, str) and u]

    def _result_mime(self) -> str:
        return "image/png"

    async def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        **kwargs: Any,
    ) -> GenerationResult:
        # width/height 是命名参数，不会进入 **kwargs；显式转发以免 _build_create_payload 读不到
        kwargs["width"] = width
        kwargs["height"] = height
        payload = self._build_create_payload(prompt, kwargs)
        result = await self._run_task(payload, self._extract_result_urls, self._result_mime())
        # 用真实字节嗅探更准确的 MIME（jpeg/png），并同步到多图 files
        from .sparkhub_base import _detect_mime
        result.mime_type = _detect_mime(result.file_bytes)
        result.files = [(b, _detect_mime(b)) for b, _ in result.files]
        return result

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        # Spark Hub 生图需参考图公网 URL；本地资产默认无公网链接，明示原因避免用户困惑。
        raise ProviderError(
            "Spark Hub Seedream 图生图需要参考图公网链接，当前本地资产暂不支持，"
            "请选择文生图，或使用支持图生的其他服务"
        )

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Spark Hub Seedream 不支持 text_to_video")

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Spark Hub Seedream 不支持 image_to_video")
