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

"""Seedance Provider - 豆包 Seedance 视频生成模型（火山引擎 ARK）。

支持 Seedance 2.0 / 2.5 预设模型的文生视频与图生视频。
API 为异步任务模式：创建任务 → 轮询状态 → 下载视频。

参考:
- 创建任务: https://www.volcengine.com/docs/82379/1520757
- 查询任务: https://www.volcengine.com/docs/82379/1521309
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from .base import BaseProvider, GenerationResult, ProviderError

# 火山引擎官方 API 域名：base_url 指向它时，video_url 已是公网 CDN，无需改写
_ARK_OFFICIAL_HOST = "ark.cn-beijing.volces.com"

# 预设模型 ID（数据驱动，便于后续扩展）
MODEL_SEEDANCE_2_0 = "doubao-seedance-2-0-260128"
MODEL_SEEDANCE_2_5 = "doubao-seedance-2-5"
DEFAULT_MODEL = MODEL_SEEDANCE_2_0  # 2.5 API 即将上线，默认回退到 2.0

# (width, height) -> (resolution, ratio) 反查表，与前端 VIDEO_SIZE_TABLE 对齐。
# 来源: https://www.volcengine.com/docs/82379/1520757
_VIDEO_SIZE_REVERSE: dict[tuple[int, int], tuple[str, str]] = {
    (864, 480): ("480p", "16:9"),
    (736, 544): ("480p", "4:3"),
    (640, 640): ("480p", "1:1"),
    (544, 736): ("480p", "3:4"),
    (480, 864): ("480p", "9:16"),
    (960, 416): ("480p", "21:9"),
    (1248, 704): ("720p", "16:9"),
    (1120, 832): ("720p", "4:3"),
    (960, 960): ("720p", "1:1"),
    (832, 1120): ("720p", "3:4"),
    (704, 1248): ("720p", "9:16"),
    (1504, 640): ("720p", "21:9"),
    (1920, 1088): ("1080p", "16:9"),
    (1664, 1248): ("1080p", "4:3"),
    (1440, 1440): ("1080p", "1:1"),
    (1248, 1664): ("1080p", "3:4"),
    (1088, 1920): ("1080p", "9:16"),
    (2176, 928): ("1080p", "21:9"),
}

# 任务终态：到达后停止轮询
_TERMINAL_STATUS = {"succeeded", "failed", "cancelled", "expired"}


def _detect_mime(image_bytes: bytes) -> str:
    """按魔数识别常见图片 MIME；未知则回退到 image/png。"""
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
        return "image/webp"
    return "image/png"


def _to_data_url(image_bytes: bytes) -> str:
    """将图片字节编码为 data URL（Seedance image_url 字段要求）。"""
    mime = _detect_mime(image_bytes)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


class SeedanceProvider(BaseProvider):
    """豆包 Seedance 视频生成 Provider（火山引擎 ARK）。"""

    SUPPORTED_TYPES = ["text2video", "img2video"]

    # 任务轮询配置
    _POLL_INTERVAL = 5.0  # 轮询间隔（秒）
    _POLL_TIMEOUT = 600.0  # 单次生成最长等待（秒）：10 分钟

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
            raise ProviderError("Seedance API Key 未配置")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _resolve_size(self, width: int, height: int) -> tuple[str | None, str | None]:
        """由前端透传的 (width, height) 反查 (resolution, ratio)；未命中返回 (None, None)。"""
        return _VIDEO_SIZE_REVERSE.get((int(width), int(height)), (None, None))

    def _build_params(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """从 kwargs 提取 Seedance API 接受的参数，未提供则省略由 API 取默认值。"""
        params: dict[str, Any] = {}
        width = kwargs.get("width")
        height = kwargs.get("height")
        if width is not None and height is not None:
            resolution, ratio = self._resolve_size(width, height)
            if resolution:
                params["resolution"] = resolution
            if ratio:
                params["ratio"] = ratio
        duration = kwargs.get("duration")
        if duration is not None:
            params["duration"] = int(duration)
        seed = kwargs.get("seed")
        if seed is not None:
            params["seed"] = int(seed)
        # 默认不加水印，避免污染生成产物；可由 config 覆盖
        params["watermark"] = bool(self.config.get("watermark", False))
        return params

    async def _create_task(
        self,
        client: httpx.AsyncClient,
        model_id: str,
        content: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> str:
        """创建视频生成任务，返回 task_id。"""
        url = f"{self.base_url}/contents/generations/tasks"
        payload = {"model": model_id, "content": content, **params}
        resp = await self._request_with_retry(
            client,
            "POST",
            url,
            provider_name="Seedance",
            headers=self._headers(),
            json=payload,
        )
        data = resp.json()
        task_id = data.get("id")
        if not task_id:
            raise ProviderError(f"Seedance 创建任务未返回 id: {data}")
        return str(task_id)

    async def _poll_task(
        self,
        client: httpx.AsyncClient,
        task_id: str,
    ) -> dict[str, Any]:
        """轮询任务状态直到终态；返回最终响应 JSON。"""
        url = f"{self.base_url}/contents/generations/tasks/{task_id}"
        elapsed = 0.0
        while elapsed < self._POLL_TIMEOUT:
            resp = await self._request_with_retry(
                client,
                "GET",
                url,
                provider_name="Seedance",
                headers=self._headers(),
            )
            data = resp.json()
            status = data.get("status")
            if status in _TERMINAL_STATUS:
                return data
            await asyncio.sleep(self._POLL_INTERVAL)
            elapsed += self._POLL_INTERVAL
        raise ProviderError(
            f"Seedance 任务 {task_id} 轮询超时（>{int(self._POLL_TIMEOUT)}s）"
        )

    def _resolve_download_url(self, video_url: str) -> str:
        """将 video_url 的 host 改写为 base_url 的 host，使其走同一 mock/代理入口。

        背景：当 base_url 指向本地 mock / 代理（如 http://host.docker.internal:23333/api/v3）时，
        服务返回的 video_url 可能是 http://localhost:23333/sample.mp4，容器内无法通过 localhost
        访问宿主机服务，需改写为 base_url 的 host（如 host.docker.internal）。
        官方公网 base_url 场景下 video_url 已是公网 CDN，不改写。
        """
        base = urlparse(self.base_url)
        if base.hostname == _ARK_OFFICIAL_HOST:
            return video_url
        target = urlparse(video_url)
        # 用 base_url 的 scheme+netloc 替换 video_url 的对应部分，保留 path/query/fragment
        return urlunparse(target._replace(scheme=base.scheme, netloc=base.netloc))

    async def _download_video(self, video_url: str) -> bytes:
        """下载生成的视频字节（CDN 链接，瞬时故障自动重试）。"""
        download_url = self._resolve_download_url(video_url)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await self._request_with_retry(
                client,
                "GET",
                download_url,
                provider_name="Seedance 视频下载",
            )
        return resp.content

    async def _generate(
        self,
        content: list[dict[str, Any]],
        kwargs: dict[str, Any],
    ) -> GenerationResult:
        model_id = kwargs.get("model_id") or self.config.get("model_id", DEFAULT_MODEL)
        params = self._build_params(kwargs)

        async with httpx.AsyncClient(timeout=120) as client:
            task_id = await self._create_task(client, model_id, content, params)
            result = await self._poll_task(client, task_id)

        status = result.get("status")
        if status != "succeeded":
            err = result.get("error") or {}
            code = err.get("code") if isinstance(err, dict) else None
            message = err.get("message") if isinstance(err, dict) else None
            raise ProviderError(
                f"Seedance 任务 {task_id} 未成功（status={status}"
                + (f", code={code}" if code else "")
                + (f"）: {message}" if message else "）")
            )

        video_url = (result.get("content") or {}).get("video_url")
        if not video_url:
            raise ProviderError(f"Seedance 任务 {task_id} 成功但未返回 video_url")
        video_bytes = await self._download_video(video_url)

        metadata: dict[str, Any] = {
            "model": model_id,
            "task_id": task_id,
        }
        for k in ("seed", "resolution", "ratio", "duration"):
            if k in result:
                metadata[k] = result[k]
        usage = result.get("usage") or {}
        total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        if isinstance(total_tokens, (int, float)) and total_tokens >= 0:
            metadata["tokens_used"] = int(total_tokens)
        return GenerationResult(
            file_bytes=video_bytes,
            mime_type="video/mp4",
            metadata=metadata,
        )

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        content = [{"type": "text", "text": prompt}]
        return await self._generate(content, kwargs)

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        if not image_bytes:
            raise ProviderError("Seedance 图生视频缺少输入图片")
        content: list[dict[str, Any]] = []
        if prompt:
            content.append({"type": "text", "text": prompt})
        content.append({"type": "image_url", "image_url": {"url": _to_data_url(image_bytes)}})
        return await self._generate(content, kwargs)

    async def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Seedance 不支持 text_to_image")

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Seedance 不支持 image_to_image")

    async def test_connection(self) -> bool:
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 200:
                return True
            raise ProviderError(f"Seedance 返回 {resp.status_code}: {resp.text[:200]}")
