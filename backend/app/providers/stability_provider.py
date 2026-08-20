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

"""Stability AI Provider（简化实现，可按需扩展）。

参考：https://platform.stability.ai/
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .base import BaseProvider, GenerationResult, ProviderError


class StabilityProvider(BaseProvider):
    SUPPORTED_TYPES = ["text2img", "img2img"]

    def __init__(
        self,
        base_url: str = "https://api.stability.ai",
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("Stability API Key 未配置")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    async def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        **kwargs: Any,
    ) -> GenerationResult:
        model_id = kwargs.get("model_id") or self.config.get("model_id", "stable-image-core")
        count = max(1, int(kwargs.get("count") or 1))

        # Stability API 每次请求返回单张图片，count > 1 时并发请求
        async def _single_request() -> bytes:
            url = f"{self.base_url}/v2beta/stable-image/generate/{model_id}"
            files = {
                "prompt": (None, prompt),
                "output_format": (None, "png"),
            }
            if negative_prompt:
                files["negative_prompt"] = (None, negative_prompt)
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await self._request_with_retry(
                    client,
                    "POST",
                    url,
                    provider_name="Stability",
                    headers=self._headers(),
                    files=files,
                )
            import base64 as _b64
            data = resp.json()
            img_b64 = data.get("image")
            if not img_b64:
                raise ProviderError("Stability 响应中未找到 image 字段")
            return _b64.b64decode(img_b64)

        if count == 1:
            img_bytes = await _single_request()
            files_list = [(img_bytes, "image/png")]
        else:
            results = await asyncio.gather(*[_single_request() for _ in range(count)])
            files_list = [(b, "image/png") for b in results]

        return GenerationResult(
            file_bytes=files_list[0][0],
            mime_type=files_list[0][1],
            metadata={"model": model_id},
            files=files_list,
        )

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Stability image_to_image 暂未实现，请使用 text_to_image 或扩展实现")

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Stability 不支持 text_to_video")

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Stability 不支持 image_to_video")

    async def test_connection(self) -> bool:
        url = f"{self.base_url}/v1/user/balance"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 200:
                return True
            raise ProviderError(f"Stability 返回 {resp.status_code}: {resp.text[:200]}")
