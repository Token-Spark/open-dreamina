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

"""Gemini Image Provider - OpenRouter Nano Banana Pro（Gemini 3 Pro Image）。

- 经 OpenRouter Chat Completions 协议调用 google/gemini-3-pro-image，
  模型文档：https://openrouter.ai/google/gemini-3-pro-image
- 请求需携带 modalities=["image", "text"]，生成图以 data URL 返回于
  choices[0].message.images[].image_url.url。
- 尺寸经 image_config 控制：宽高映射到最接近的 aspect_ratio 档位，
  像素规模映射到 1K/2K/4K 分辨率档位。
- 图生图（编辑）：参考图转 data URL 附加在消息中，单次请求上限 14 张。
"""
from __future__ import annotations

import asyncio
import base64
import math
from typing import Any

import httpx

from .base import BaseProvider, GenerationResult, ProviderError

# OpenRouter 模型标识（Nano Banana Pro）
MODEL_GEMINI_3_PRO_IMAGE = "google/gemini-3-pro-image"

# image_config.aspect_ratio 支持的全部档位：(比例, 参考宽, 参考高)
_ASPECT_RATIOS: list[tuple[str, int, int]] = [
    ("1:1", 1024, 1024),
    ("2:3", 832, 1248),
    ("3:2", 1248, 832),
    ("3:4", 864, 1184),
    ("4:3", 1184, 864),
    ("4:5", 896, 1152),
    ("5:4", 1152, 896),
    ("9:16", 768, 1344),
    ("16:9", 1344, 768),
    ("21:9", 1536, 672),
]

# image_config.image_size 支持的档位：(档位名, 代表像素数)
_IMAGE_SIZES: list[tuple[str, int]] = [
    ("1K", 1024 * 1024),
    ("2K", 2048 * 2048),
    ("4K", 4096 * 4096),
]

# 模型单次请求的参考图上限
_MAX_REFERENCE_IMAGES = 14

# 生成耗时随分辨率上升（4K 可达数分钟），放宽超时
_REQUEST_TIMEOUT = 300


def _detect_mime(image_bytes: bytes) -> str:
    """按魔数识别常见图片 MIME；未知则回退到 image/png。"""
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
        return "image/webp"
    return "image/png"


class GeminiImageProvider(BaseProvider):
    """OpenRouter Gemini 3 Pro Image（Nano Banana Pro）。"""

    SUPPORTED_TYPES = ["text2img", "img2img"]

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("OpenRouter API Key 未配置")
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
        return await self._generate(prompt, negative_prompt, [], width, height, **kwargs)

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        # Chat Completions 协议无 strength 参数，编辑幅度由 prompt 表达；
        # 宽高/负面词等经 worker 透传落在 kwargs 中，此处先取出，
        # 避免位置实参与 kwargs 同名参数重复绑定
        negative_prompt = str(kwargs.pop("negative_prompt", "") or "")
        width = int(kwargs.pop("width", 1024) or 1024)
        height = int(kwargs.pop("height", 1024) or 1024)
        return await self._generate(prompt, negative_prompt, image_bytes, width, height, **kwargs)

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Gemini 不支持 text_to_video")

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Gemini 不支持 image_to_video")

    async def test_connection(self) -> bool:
        # OpenRouter /auth/key 端点用于校验 API Key 并返回额度信息
        url = f"{self.base_url}/auth/key"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 200:
                return True
            raise ProviderError(f"OpenRouter 返回 {resp.status_code}: {resp.text[:200]}")

    async def _generate(
        self,
        prompt: str,
        negative_prompt: str,
        reference_images: list[bytes],
        width: int = 1024,
        height: int = 1024,
        **kwargs: Any,
    ) -> GenerationResult:
        model_id = kwargs.get("model_id") or self.config.get("model_id", MODEL_GEMINI_3_PRO_IMAGE)
        width = int(kwargs.get("width") or width)
        height = int(kwargs.get("height") or height)
        negative_prompt = negative_prompt or str(kwargs.get("negative_prompt") or "")
        count = max(1, int(kwargs.get("count") or 1))
        aspect_ratio = self._closest_aspect_ratio(width, height)
        image_size = (
            str(kwargs.get("image_size") or self.config.get("image_size") or "")
            or self._infer_image_size(width, height)
        )

        content: list[dict[str, Any]] = [
            {"type": "text", "text": self._compose_prompt(prompt, negative_prompt)}
        ]
        for image in reference_images[:_MAX_REFERENCE_IMAGES]:
            data_url = f"data:{_detect_mime(image)};base64,{base64.b64encode(image).decode('ascii')}"
            content.append({"type": "image_url", "image_url": {"url": data_url}})

        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": content}],
            "modalities": ["image", "text"],
            "image_config": {"aspect_ratio": aspect_ratio, "image_size": image_size},
        }

        # 单次响应通常只含 1 张图，多图并发发起多次请求
        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            responses = await asyncio.gather(*[
                self._request_with_retry(
                    client,
                    "POST",
                    url,
                    provider_name="GeminiImage",
                    headers=self._headers(),
                    json=payload,
                )
                for _ in range(count)
            ])
            files: list[tuple[bytes, str]] = []
            tokens_used: int | None = None
            for resp in responses:
                data = resp.json()
                files.extend(await self._extract_images(data, client))
                total_tokens = (data.get("usage") or {}).get("total_tokens")
                if isinstance(total_tokens, (int, float)) and total_tokens >= 0:
                    tokens_used = int(total_tokens)

        metadata: dict[str, Any] = {
            "model": model_id,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        }
        if tokens_used is not None:
            metadata["tokens_used"] = tokens_used
        return GenerationResult(
            file_bytes=files[0][0],
            mime_type=files[0][1],
            metadata=metadata,
            files=files,
        )

    async def _extract_images(
        self,
        data: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> list[tuple[bytes, str]]:
        """从 Chat Completions 响应提取生成图片，兼容 data URL 与公网 URL 两种返回。"""
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"GeminiImage 响应无 choices: {data.get('error') or data}")
        message = choices[0].get("message") or {}
        files: list[tuple[bytes, str]] = []
        for image in message.get("images") or []:
            image_url = (image.get("image_url") or {}).get("url") or image.get("url")
            if not image_url:
                continue
            if image_url.startswith("data:"):
                header, _, b64_payload = image_url.partition(",")
                mime = header.removeprefix("data:").split(";", 1)[0] or "image/png"
                files.append((base64.b64decode(b64_payload), mime))
            else:
                # 兼容网关返回公网图片 URL 的场景
                dl = await self._request_with_retry(
                    client, "GET", image_url, provider_name="GeminiImage 图片下载",
                )
                files.append((dl.content, _detect_mime(dl.content)))
        if not files:
            # 失败原因常在 assistant 文本回复中（如内容安全拦截）
            detail = message.get("content") or data
            raise ProviderError(f"GeminiImage 响应中未找到生成图片: {str(detail)[:300]}")
        return files

    @staticmethod
    def _compose_prompt(prompt: str, negative_prompt: str) -> str:
        """协议不支持 negative_prompt，转为正向提示词后缀。"""
        if not negative_prompt:
            return prompt
        return f"{prompt}\n\n避免出现以下元素: {negative_prompt}"

    @staticmethod
    def _closest_aspect_ratio(width: int, height: int) -> str:
        """按纵横比对数距离，映射到模型支持的最接近 aspect_ratio 档位。"""
        target = math.log(width / height)
        ratio, _, _ = min(
            _ASPECT_RATIOS,
            key=lambda entry: abs(math.log(entry[1] / entry[2]) - target),
        )
        return ratio

    @staticmethod
    def _infer_image_size(width: int, height: int) -> str:
        """按像素总数对数距离，映射到 1K/2K/4K 中最接近的分辨率档位。"""
        target = math.log(max(1, width * height))
        size, _ = min(
            _IMAGE_SIZES,
            key=lambda entry: abs(math.log(entry[1]) - target),
        )
        return size
