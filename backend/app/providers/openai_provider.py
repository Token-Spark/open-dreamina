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

"""OpenAI Provider - GPT Image 2（官方 API 或 OpenRouter 等统一网关）。

- slug `openai` 标识「OpenAI 兼容的图片生成接口」，与具体供应商解耦：
  官方 api.openai.com 或 OpenRouter（https://openrouter.ai/api/v1）均可接入。
- 按接入方分两种协议，由 base_url 自动识别（OpenRouter 等统一网关按 host 判断）：
  * 官方协议：文生图 POST /images/generations（JSON），
    图生图 POST /images/edits（multipart 表单，image[] 承载多张参考图）。
  * 统一网关协议：未实现 /images/edits 路由（请求返回 404），图生图复用
    /images/generations 并以 input_references（data URL）携带参考图，
    且模型 ID 需厂商前缀（如 openai/gpt-image-2）。
- 两种协议响应同构（data[].b64_json + usage.total_tokens），由 _parse_images_response 统一解析。
- 协议无 strength/negative_prompt/steps，编辑幅度由 prompt 表达（与 Gemini 协议一致）。
"""
from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlparse

import httpx

from .base import BaseProvider, GenerationResult, ProviderError

# OpenAI 默认图片生成模型（GPT Image 2）
MODEL_GPT_IMAGE_2 = "gpt-image-2"

# 生成耗时随画质/尺寸上升（OpenRouter p95 约 120s），对齐 Gemini provider 放宽超时
_REQUEST_TIMEOUT = 300


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

    @property
    def _unified_gateway(self) -> bool:
        """是否为 OpenRouter 等统一网关：未实现 /images/edits（404），模型 ID 需厂商前缀。"""
        host = (urlparse(self.base_url).hostname or "").lower()
        return "openrouter" in host

    def _gateway_model_id(self, model_id: str) -> str:
        """统一网关要求厂商前缀模型 ID；裸 ID 自动补 openai/，已带前缀的保持不变。"""
        if self._unified_gateway and "/" not in model_id:
            return f"openai/{model_id}"
        return model_id

    @staticmethod
    def _accepts_response_format(model_id: str) -> bool:
        """仅 dall-e 系列需要 response_format；gpt-image 系列恒返回 b64，传了会被官方拒绝。"""
        return not model_id.split("/")[-1].startswith("gpt-image")

    async def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        **kwargs: Any,
    ) -> GenerationResult:
        model_id = self._gateway_model_id(
            kwargs.get("model_id") or self.config.get("model_id", MODEL_GPT_IMAGE_2)
        )
        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "n": max(1, int(kwargs.get("count") or 1)),
            "size": self._size_str(width, height),
        }
        if self._accepts_response_format(model_id):
            payload["response_format"] = "b64_json"
        resp = await self._post_generations(payload)
        return self._parse_images_response(resp.json(), model_id)

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        model_id = self._gateway_model_id(
            kwargs.get("model_id") or self.config.get("model_id", MODEL_GPT_IMAGE_2)
        )
        width = int(kwargs.get("width") or 1024)
        height = int(kwargs.get("height") or 1024)
        count = max(1, int(kwargs.get("count") or 1))

        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "n": count,
            "size": self._size_str(width, height),
        }
        if self._accepts_response_format(model_id):
            payload["response_format"] = "b64_json"

        if self._unified_gateway:
            return await self._generate_with_references(payload, image_bytes)
        return await self._edit_multipart(payload, image_bytes)

    async def _post_generations(self, payload: dict[str, Any]) -> httpx.Response:
        """POST /images/generations（JSON）：文生图与统一网关图生图共用。"""
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            return await self._request_with_retry(
                client,
                "POST",
                f"{self.base_url}/images/generations",
                provider_name="OpenAI",
                headers=self._headers(),
                json=payload,
            )

    async def _generate_with_references(
        self,
        payload: dict[str, Any],
        image_bytes: list[bytes],
    ) -> GenerationResult:
        """统一网关协议：参考图以 input_references（data URL）随 JSON 提交。"""
        payload["input_references"] = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(img).decode('ascii')}"
                },
            }
            for img, mime, _ in map(self._image_file_field, image_bytes)
        ]
        resp = await self._post_generations(payload)
        return self._parse_images_response(resp.json(), payload["model"])

    async def _edit_multipart(
        self,
        payload: dict[str, Any],
        image_bytes: list[bytes],
    ) -> GenerationResult:
        """官方协议：/images/edits multipart 表单，image[] 数组字段承载多张参考图。"""
        headers = self._headers()
        # multipart 边界由 httpx 按表单自动生成，显式指定 Content-Type 会破坏 boundary
        headers.pop("Content-Type", None)
        files = [
            ("image[]", (f"image_{i}.{ext}", img, mime))
            for i, (img, mime, ext) in enumerate(map(self._image_file_field, image_bytes))
        ]
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await self._request_with_retry(
                client,
                "POST",
                f"{self.base_url}/images/edits",
                provider_name="OpenAI",
                headers=headers,
                data={key: str(value) for key, value in payload.items()},
                files=files,
            )
        return self._parse_images_response(resp.json(), payload["model"])

    @staticmethod
    def _parse_images_response(data: dict[str, Any], model_id: str) -> GenerationResult:
        """解析 /images/generations 与 /images/edits 的同构响应（data[].b64_json + usage）。"""
        items = data.get("data") or []
        if not items or "b64_json" not in items[0]:
            raise ProviderError(f"OpenAI 响应中未找到 b64_json: {str(data)[:300]}")

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
                # 统一网关在 media_type 中标注实际格式；官方 gpt-image 默认 png
                files.append((base64.b64decode(b64), item.get("media_type") or "image/png"))
        if not files:
            raise ProviderError("OpenAI 响应 data 中未包含可用图片")

        return GenerationResult(
            file_bytes=files[0][0],
            mime_type=files[0][1],
            metadata=metadata,
            files=files,
        )

    @staticmethod
    def _image_file_field(image_bytes: bytes) -> tuple[bytes, str, str]:
        """把参考图字节转为 (bytes, mime, ext)；按魔数识别格式，未知回退 png（各端点均接受 png/jpeg/webp）。"""
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return image_bytes, "image/jpeg", "jpg"
        if image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
            return image_bytes, "image/webp", "webp"
        return image_bytes, "image/png", "png"

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
