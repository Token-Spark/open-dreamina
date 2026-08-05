"""阿里·通义万相 Provider（简化实现）。"""
from __future__ import annotations

from typing import Any

import httpx

from .base import BaseProvider, GenerationResult, ProviderError


class DashScopeProvider(BaseProvider):
    SUPPORTED_TYPES = ["text2img", "img2img"]

    def __init__(
        self,
        base_url: str = "https://dashscope.aliyuncs.com",
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("DashScope API Key 未配置")
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
        model_id = kwargs.get("model_id") or self.config.get("model_id", "wanx-v1")
        url = f"{self.base_url}/api/v1/services/aigc/text2image/image-synthesis"
        payload = {
            "model": model_id,
            "input": {"prompt": prompt},
            "parameters": {
                "size": f"{width}*{height}",
                "n": 1,
            },
        }
        if negative_prompt:
            payload["input"]["negative_prompt"] = negative_prompt

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
        if resp.status_code != 200:
            raise ProviderError(f"DashScope 返回 {resp.status_code}: {resp.text}")
        data = resp.json()
        # 通义万相通常是异步任务，这里简化：如有 output.results 立即返回
        results = (data.get("output") or {}).get("results") or []
        if not results:
            raise ProviderError("DashScope 未返回结果（可能为异步任务，需扩展轮询）")
        image_url = results[0].get("url")
        if not image_url:
            raise ProviderError("DashScope 响应中未找到 image url")
        async with httpx.AsyncClient(timeout=60) as client:
            img_resp = await client.get(image_url)
        if img_resp.status_code != 200:
            raise ProviderError(f"下载结果图片失败: {img_resp.status_code}")
        # 通义万相响应 usage 中含 input_tokens/output_tokens（计费维度），合并为 tokens_used
        usage = data.get("usage") or {}
        input_tokens = usage.get("input_tokens") if isinstance(usage, dict) else 0
        output_tokens = usage.get("output_tokens") if isinstance(usage, dict) else 0
        tokens_used = None
        if isinstance(input_tokens, (int, float)) or isinstance(output_tokens, (int, float)):
            tokens_used = int((input_tokens or 0) + (output_tokens or 0))
        metadata: dict[str, Any] = {"model": model_id}
        if tokens_used is not None and tokens_used >= 0:
            metadata["tokens_used"] = tokens_used
        return GenerationResult(
            file_bytes=img_resp.content,
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
        raise ProviderError("DashScope image_to_image 暂未实现")

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("DashScope text_to_video 暂未实现")

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("DashScope image_to_video 暂未实现")

    async def test_connection(self) -> bool:
        # 简单校验：API Key 非空即认为通过（避免消耗额度）
        return bool(self.api_key)
