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

"""Seedream Provider - 豆包 Seedream 图像生成模型（火山引擎 ARK）。"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from .base import BaseProvider, GenerationResult, ProviderError

# 火山引擎官方 API 域名：base_url 指向它时，图片 URL 已是公网 CDN，无需改写
_ARK_OFFICIAL_HOST = "ark.cn-beijing.volces.com"


def _detect_mime(image_bytes: bytes) -> str:
    """按魔数识别常见图片 MIME；未知则回退到 image/png。"""
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
        return "image/webp"
    return "image/png"


class SeedreamProvider(BaseProvider):
    SUPPORTED_TYPES = ["text2img", "img2img"]

    def __init__(
        self,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}

    def _resolve_url(self, image_url: str) -> str:
        """将图片 URL 的 host 改写为 base_url 的 host，使其走同一 mock/代理入口。

        背景：当 base_url 指向本地 mock / 代理（如 http://host.docker.internal:23333/api/v3）时，
        服务返回的图片 URL 可能是 http://localhost:23333/sample.jpg，容器内无法通过 localhost
        访问宿主机服务，需改写为 base_url 的 host（如 host.docker.internal）。
        官方公网 base_url 场景下图片 URL 已是公网 CDN，不改写。
        """
        base = urlparse(self.base_url)
        if base.hostname == _ARK_OFFICIAL_HOST:
            return image_url
        target = urlparse(image_url)
        return urlunparse(target._replace(scheme=base.scheme, netloc=base.netloc))

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("Seedream API Key 未配置")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
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
        model_id = kwargs.get("model_id") or self.config.get("model_id", "doubao-seedream-5-0-pro-260628")
        url = f"{self.base_url}/images/generations"
        payload = {
            "model": model_id,
            "prompt": prompt,
            "size": f"{width}x{height}",
            "n": 1,
            "response_format": "b64_json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await self._request_with_retry(
                client,
                "POST",
                url,
                provider_name="Seedream",
                headers=self._headers(),
                json=payload,
            )
        data = resp.json()
        items = data.get("data") or []
        if not items:
            raise ProviderError(f"Seedream 响应中未找到 data: {data}")
        item = items[0]
        b64_json = item.get("b64_json")
        if b64_json:
            import base64 as _b64
            file_bytes = _b64.b64decode(b64_json)
            mime_type = "image/png"
        else:
            # 部分网关/mock 不返回 b64_json，仅返回可下载的 url（且 host 常是 localhost）
            image_url = item.get("url")
            if not image_url:
                raise ProviderError(f"Seedream 响应中既无 b64_json 也无 url: {data}")
            async with httpx.AsyncClient(timeout=120) as client:
                dl = await self._request_with_retry(
                    client,
                    "GET",
                    self._resolve_url(image_url),
                    provider_name="Seedream 图片下载",
                )
            file_bytes = dl.content
            mime_type = _detect_mime(file_bytes)
        metadata: dict[str, Any] = {"model": model_id}
        return GenerationResult(
            file_bytes=file_bytes,
            mime_type=mime_type,
            metadata=metadata,
        )

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Seedream image_to_image 暂未实现")

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Seedream 不支持 text_to_video")

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Seedream 不支持 image_to_video")

    async def test_connection(self) -> bool:
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 200:
                return True
            raise ProviderError(f"Seedream 返回 {resp.status_code}: {resp.text[:200]}")
