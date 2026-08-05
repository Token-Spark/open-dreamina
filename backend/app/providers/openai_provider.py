"""OpenAI Provider - DALL·E 3 / GPT-4o Image（简化实现）。"""
from __future__ import annotations

from typing import Any

import httpx

from .base import BaseProvider, GenerationResult, ProviderError


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
        model_id = kwargs.get("model_id") or self.config.get("model_id", "dall-e-3")
        size = self._size_str(width, height)
        url = f"{self.base_url}/images/generations"
        payload = {
            "model": model_id,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
        if resp.status_code != 200:
            raise ProviderError(f"OpenAI 返回 {resp.status_code}: {resp.text}")
        data = resp.json()
        items = data.get("data") or []
        if not items or "b64_json" not in items[0]:
            raise ProviderError("OpenAI 响应中未找到 b64_json")
        import base64 as _b64
        # DALL·E 响应通常不带 usage；新版 gpt-image-1 等模型可能在 usage 中返回 token 用量
        usage = data.get("usage") or {}
        total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        metadata: dict[str, Any] = {"model": model_id}
        if isinstance(total_tokens, (int, float)) and total_tokens >= 0:
            metadata["tokens_used"] = int(total_tokens)
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
            try:
                resp = await client.get(url, headers=self._headers())
                return resp.status_code == 200
            except Exception:
                return False

    @staticmethod
    def _size_str(width: int, height: int) -> str:
        # DALL·E 3 仅支持 1024x1024 / 1792x1024 / 1024x1792
        for w, h in [(1024, 1024), (1792, 1024), (1024, 1792)]:
            if abs(width - w) < 100 and abs(height - h) < 100:
                return f"{w}x{h}"
        return "1024x1024"
