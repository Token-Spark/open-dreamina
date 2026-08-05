"""Stability AI Provider（简化实现，可按需扩展）。

参考：https://platform.stability.ai/
"""
from __future__ import annotations

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
        url = f"{self.base_url}/v2beta/stable-image/generate/{model_id}"
        files = {
            "prompt": (None, prompt),
            "output_format": (None, "png"),
        }
        if negative_prompt:
            files["negative_prompt"] = (None, negative_prompt)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=self._headers(), files=files)
        if resp.status_code != 200:
            raise ProviderError(f"Stability 返回 {resp.status_code}: {resp.text}")
        data = resp.json()
        import base64 as _b64
        img_b64 = data.get("image")
        if not img_b64:
            raise ProviderError("Stability 响应中未找到 image 字段")
        return GenerationResult(
            file_bytes=_b64.b64decode(img_b64),
            mime_type="image/png",
            metadata={"model": model_id},
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
            try:
                resp = await client.get(url, headers=self._headers())
                return resp.status_code == 200
            except Exception:
                return False
