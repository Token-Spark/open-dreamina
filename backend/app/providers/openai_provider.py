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

"""OpenAI Provider - GPT Image 2（兼容 OpenRouter 等 OpenAI 兼容网关）。

- slug `openai` 标识「OpenAI 兼容的图片生成接口」，与具体供应商解耦：
  官方 api.openai.com 或 OpenRouter（https://openrouter.ai/api/v1）均可接入。
- OpenAI 当前图片生成模型为 GPT Image 2（model id: gpt-image-2），
  模型文档：https://openrouter.ai/openai/gpt-image-2
"""
from __future__ import annotations

from typing import Any

import httpx

from .base import BaseProvider, GenerationResult, ProviderError

# OpenAI 默认图片生成模型（GPT Image 2）
MODEL_GPT_IMAGE_2 = "gpt-image-2"


class OpenAIProvider(BaseProvider):
    SUPPORTED_TYPES = ["text2img", "img2img"]

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("OpenAI API Key 未配置")
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
        model_id = kwargs.get("model_id") or self.config.get("model_id", MODEL_GPT_IMAGE_2)
        size = self._size_str(width, height)
        count = max(1, int(kwargs.get("count") or 1))
        url = f"{self.base_url}/images/generations"
        payload = {
            "model": model_id,
            "prompt": prompt,
            "n": count,
            "size": size,
            "response_format": "b64_json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await self._request_with_retry(
                client,
                "POST",
                url,
                provider_name="OpenAI",
                headers=self._headers(),
                json=payload,
            )
        data = resp.json()
        items = data.get("data") or []
        if not items or "b64_json" not in items[0]:
            raise ProviderError("OpenAI 响应中未找到 b64_json")
        import base64 as _b64

        # GPT Image 系列在 usage 中返回 token 用量；部分兼容网关可能省略
        usage = data.get("usage") or {}
        total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        metadata: dict[str, Any] = {"model": model_id}
        if isinstance(total_tokens, (int, float)) and total_tokens >= 0:
            metadata["tokens_used"] = int(total_tokens)

        files: list[tuple[bytes, str]] = []
        for item in items:
            b64 = item.get("b64_json")
            if b64:
                files.append((_b64.b64decode(b64), "image/png"))

        return GenerationResult(
            file_bytes=files[0][0],
            mime_type=files[0][1],
            metadata=metadata,
            files=files,
        )

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("OpenAI image_to_image 暂未实现")

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("OpenAI 不支持 text_to_video")

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("OpenAI 不支持 image_to_video")

    async def test_connection(self) -> bool:
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 200:
                return True
            raise ProviderError(f"OpenAI 返回 {resp.status_code}: {resp.text[:200]}")

    @staticmethod
    def _size_str(width: int, height: int) -> str:
        # GPT Image 2 支持 1024x1024 / 1536x1024 / 1024x1536
        if width > height:
            return "1536x1024"
        if height > width:
            return "1024x1536"
        return "1024x1024"
