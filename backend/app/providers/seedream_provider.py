"""Seedream Provider - 豆包 Seedream 图像生成模型（火山引擎 ARK）。"""
from __future__ import annotations

from typing import Any

import httpx

from .base import BaseProvider, GenerationResult, ProviderError


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
        if not items or "b64_json" not in items[0]:
            raise ProviderError("Seedream 响应中未找到 b64_json")
        import base64 as _b64
        metadata: dict[str, Any] = {"model": model_id}
        return GenerationResult(
            file_bytes=_b64.b64decode(items[0]["b64_json"]),
            mime_type="image/png",
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
            try:
                resp = await client.get(url, headers=self._headers())
                return resp.status_code == 200
            except Exception:
                return False
