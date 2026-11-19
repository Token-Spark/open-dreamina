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

Seedance 2.5 额外支持：
- 样片模式（``draft=true``，仅 480p）与基于样片任务 ID 出正式片（``content[].draft_task``）；
- 全模态参考：图片（base64）、视频（公网 URL / asset://）、音频（base64 / 公网 URL），
  通过 ``omni_reference_task_type`` 选择 reference / edit / extend；
- 原生同步音轨（``generate_audio``）、输出格式（``output_format``）。

参考:
- 创建任务: https://console.volcengine.com/ark/region:cn-beijing/docs/create-video-generation-task-api.md
- 查询任务: https://www.volcengine.com/docs/82379/1521309
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from .base import BaseProvider, GenerationResult, ProviderError
from ..utils.http_client import get_async_client

logger = logging.getLogger(__name__)

# 火山引擎官方 API 域名：base_url 指向它时，video_url 已是公网 CDN，无需改写
_ARK_OFFICIAL_HOST = "ark.cn-beijing.volces.com"

# 预设模型 ID（数据驱动，便于后续扩展）
MODEL_SEEDANCE_2_0 = "doubao-seedance-2-0-260128"
MODEL_SEEDANCE_2_5 = "doubao-seedance-2-5-260628"
DEFAULT_MODEL = MODEL_SEEDANCE_2_0

# 前端 2160p 档位在方舟 API 中写作 4k。
_RESOLUTION_ALIAS = {"2160p": "4k", "4k": "4k"}

# 2.5 全模态参考素材上限（图 / 视频 / 音频）；2.0 系列为 9/3/3。
_REF_CAPS_25 = {"image": 30, "video": 10, "audio": 10}
_REF_CAPS_20 = {"image": 9, "video": 3, "audio": 3}

# (width, height) -> (resolution, ratio) 反查表，与前端 VIDEO_SIZE_TABLE 对齐。
# 来源: https://www.volcengine.com/docs/82379/1520757
# 说明：这些像素组合只用于反查 resolution/ratio 字符串，请求体里并不发送像素值；
# 故保留 2.0 历史组合，另补 4K 组合（前后端同表）即可，2.5 亦接受同样的档位。
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
    (3840, 2176): ("4k", "16:9"),
    (3328, 2496): ("4k", "4:3"),
    (2880, 2880): ("4k", "1:1"),
    (2496, 3328): ("4k", "3:4"),
    (2176, 3840): ("4k", "9:16"),
    (4352, 1856): ("4k", "21:9"),
}

# 任务终态：到达后停止轮询
_TERMINAL_STATUS = {"succeeded", "failed", "cancelled", "expired"}


def _is_seedance25(model_id: str) -> bool:
    """2.5 的各种写法（2_5 / 2-5 / 2.5）都识别。"""
    mid = (model_id or "").lower()
    return "2_5" in mid or "2-5" in mid or "2.5" in mid


def _ref_caps(model_id: str) -> dict[str, int]:
    return _REF_CAPS_25 if _is_seedance25(model_id) else _REF_CAPS_20


def _detect_mime(image_bytes: bytes) -> str:
    """按魔数识别常见图片 MIME；未知则回退到 image/png。"""
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
        return "image/webp"
    return "image/png"


def _detect_audio_mime(audio_bytes: bytes) -> str:
    """按魔数识别 wav / mp3；未知按 wav 处理（方舟两者都支持）。"""
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "audio/wav"
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    return "audio/wav"


def _to_data_url(data: bytes, mime: str) -> str:
    """将素材字节编码为方舟 content.*_url.url 接受的 data URL。"""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _to_image_data_url(image_bytes: bytes) -> str:
    return _to_data_url(image_bytes, _detect_mime(image_bytes))


def _to_audio_data_url(audio_bytes: bytes) -> str:
    return _to_data_url(audio_bytes, _detect_audio_mime(audio_bytes))


def _build_content(kind: str, url: str, role: str | None = None) -> dict[str, Any]:
    """构造 Seedance content 元素。kind ∈ text|image_url|video_url|audio_url|draft_task。

    role 合法取值（详见官方文档 content.role）：
    - image_url：first_frame / last_frame / reference_image
    - video_url：reference_video
    - audio_url：reference_audio
    """
    item: dict[str, Any] = {"type": kind, kind: {"url": url}} if kind != "text" else {"type": "text", "text": url}
    if role:
        item["role"] = role
    return item


def _build_draft_task_content(task_id: str) -> dict[str, Any]:
    """构造基于样片任务 ID 出正式片的 content 元素。"""
    return {"type": "draft_task", "draft_task": {"id": str(task_id)}}


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

    def _build_params(self, kwargs: dict[str, Any], model_id: str) -> dict[str, Any]:
        """从 kwargs 提取 Seedance API 接受的参数，未提供则省略由 API 取默认值。

        强校验模式下，模型不支持的参数会直接报错，因此这里按模型能力筛选：
        - seed：仅 Seedance 1.0 pro/fast 支持，2.0/2.5 一律不传；
        - draft / omni_reference_task_type / output_format：仅 2.5 支持；
        - generate_audio：2.5 / 2.0 支持。
        """
        params: dict[str, Any] = {}
        is_25 = _is_seedance25(model_id)

        resolution: str | None = None
        ratio: str | None = None
        width = kwargs.get("width")
        height = kwargs.get("height")
        if width is not None and height is not None:
            r, ra = self._resolve_size(width, height)
            resolution = r
            ratio = ra
        # 显式 resolution（CLI --resolution）优先；2160p -> 4k
        explicit_res = kwargs.get("resolution")
        if isinstance(explicit_res, str) and explicit_res:
            resolution = _RESOLUTION_ALIAS.get(explicit_res.lower(), explicit_res)
        if resolution:
            params["resolution"] = resolution
        if ratio:
            params["ratio"] = ratio

        duration = kwargs.get("duration")
        if duration is not None:
            params["duration"] = int(duration)

        # seed 仅 1.0 pro/fast；本项目预设为 2.0/2.5，默认不下发
        supports_seed = ("1-0-pro" in model_id.lower()) or ("1-0-fast" in model_id.lower())
        seed = kwargs.get("seed")
        if supports_seed and seed is not None:
            params["seed"] = int(seed)

        generate_audio = kwargs.get("generate_audio")
        if generate_audio is not None:
            params["generate_audio"] = bool(generate_audio)

        if is_25:
            omni = kwargs.get("omni_reference_task_type")
            if omni in ("auto", "reference", "edit", "extend"):
                params["omni_reference_task_type"] = omni
            output_format = kwargs.get("output_format")
            if output_format in ("mp4", "mov"):
                params["output_format"] = output_format

            # 样片模式：仅支持 480p，其他分辨率会被上游拒绝
            draft = kwargs.get("draft")
            if draft is not None:
                draft_on = draft in (True, 1, "1", "true", "True")
                params["draft"] = draft_on
                if draft_on:
                    params["resolution"] = "480p"

            # 视频编辑/延长与首尾帧任务：ratio 仅支持 adaptive；edit 时长固定 -1
            if params.get("omni_reference_task_type") in ("edit", "extend"):
                params["ratio"] = "adaptive"
                if params["omni_reference_task_type"] == "edit":
                    params["duration"] = -1
            if kwargs.get("_frame_mode") == "first_last":
                params["ratio"] = "adaptive"

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
            timeout=120,
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
                timeout=120,
                headers=self._headers(),
            )
            data = resp.json()
            status = data.get("status")
            if status in _TERMINAL_STATUS:
                return data
            await asyncio.sleep(self._POLL_INTERVAL)
            elapsed += self._POLL_INTERVAL
        raise ProviderError(
            f"Seedance 任务 {task_id} 轮询超时（>{int(self._POLL_TIMEOUT)}s）。"
            "重试将从已有任务断点续查，不会重复提交",
            submit_id=task_id,
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
        resp = await self._request_with_retry(
            get_async_client(),
            "GET",
            download_url,
            provider_name="Seedance 视频下载",
            timeout=120,
        )
        return resp.content

    def _build_multimodal_content(
        self,
        primary_bytes: bytes,
        kwargs: dict[str, Any],
        model_id: str,
    ) -> list[dict[str, Any]]:
        """按 2.5 全模态参考规则构造 content（图/视频/音频各为独立元素）。

        - 图片：本地字节 → base64 data URL，role=reference_image；
        - 视频：公网 URL / asset://（方舟不支持视频 base64），role=reference_video；
        - 音频：本地字节 → base64 data URL 或公网 URL，role=reference_audio。
        """
        content: list[dict[str, Any]] = []
        caps = _ref_caps(model_id)

        images: list[bytes] = []
        if isinstance(primary_bytes, bytes) and primary_bytes:
            images.append(primary_bytes)
        for img in kwargs.get("reference_image_bytes_list") or []:
            if isinstance(img, bytes) and img:
                images.append(img)
        for img in images[: caps["image"]]:
            content.append(_build_content("image_url", _to_image_data_url(img), "reference_image"))

        video_urls = [
            u for u in (kwargs.get("reference_video_urls") or [])
            if isinstance(u, str) and u
        ][: caps["video"]]
        for url in video_urls:
            content.append(_build_content("video_url", url, "reference_video"))

        audio_items = kwargs.get("reference_audio_bytes_list") or []
        audio_urls = [u for u in (kwargs.get("reference_audio_urls") or []) if isinstance(u, str) and u]
        audio_sources: list[str] = audio_urls + [
            _to_audio_data_url(b) for b in audio_items if isinstance(b, bytes) and b
        ]
        for url in audio_sources[: caps["audio"]]:
            content.append(_build_content("audio_url", url, "reference_audio"))

        # 有参考素材时显式声明 reference，避免 auto 在参数不兼容时异步报错
        if content and "omni_reference_task_type" not in kwargs:
            kwargs["omni_reference_task_type"] = "reference"
        return content

    async def _generate(
        self,
        content: list[dict[str, Any]],
        kwargs: dict[str, Any],
    ) -> GenerationResult:
        model_id = kwargs.get("model_id") or self.config.get("model_id", DEFAULT_MODEL)

        # 基于样片任务 ID 出正式片：content 只保留 draft_task（+可选文本），
        # 其余参数由模型自动复用，禁止重复传入，故 params 置空。
        draft_task_id = kwargs.get("draft_task_id")
        if draft_task_id:
            text = next((c.get("text") for c in content if c.get("type") == "text"), None)
            content = ([{"type": "text", "text": text}] if text else []) + [
                _build_draft_task_content(str(draft_task_id))
            ]
            params: dict[str, Any] = {}
        else:
            params = self._build_params(kwargs, model_id)

        client = get_async_client()
        # 断点续查：上一轮轮询超时 / 下载失败后，上游任务仍然存在，
        # 直接用已落库的 task_id 继续查询，避免重新 create_task 二次扣费。
        resume_id = kwargs.get("submit_id")
        if resume_id:
            task_id = str(resume_id)
            logger.info("Seedance 断点续查: task_id=%s", task_id)
        else:
            task_id = await self._create_task(client, model_id, content, params)

        try:
            result = await self._poll_task(client, task_id)

            status = result.get("status")
            if status != "succeeded":
                # 上游终态失败：不携带 submit_id，让用户重试时能重新提交任务
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
            if draft_task_id:
                metadata["draft_task_id"] = str(draft_task_id)
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
        except ProviderError:
            # 由抛出方决定是否可续查（超时带 submit_id，终态失败不带）
            raise
        except Exception as exc:
            # 下载等环节的意外失败：任务已在上游，必须让 worker 记住 id
            raise ProviderError(f"{type(exc).__name__}: {exc}", submit_id=task_id) from exc

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        # worker 以 **kwargs 展开调用时 duration 会绑定到具名形参而非进入 kwargs，
        # 需回填，否则 _build_params 读取不到并省略该参数（上游退化为默认时长）。
        kwargs["duration"] = duration
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}] if prompt else []
        # 仅文本 + 视频/音频参考（无图片）也属全模态参考
        if any(
            kwargs.get(k)
            for k in ("reference_video_urls", "reference_audio_urls", "reference_audio_bytes_list")
        ):
            content.extend(self._build_multimodal_content(
                b"", kwargs, kwargs.get("model_id") or self.config.get("model_id", DEFAULT_MODEL)
            ))
        return await self._generate(content, kwargs)

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        """图生视频 / 全模态参考生视频。

        ``kwargs["frame_mode"]`` 指定图片用法：

        - ``first``（默认）：单首帧，对应 ``role=first_frame``（可省略）。
        - ``first_last``：首尾帧，需同时提供 ``kwargs["last_image_bytes"]``，
          两张图片分别携带 ``role=first_frame`` / ``role=last_frame``（2.5 ratio 强制 adaptive）。
        - ``reference``：全模态参考，图片 ``role=reference_image``，并支持
          ``reference_video_urls``（公网 URL / asset://）、``reference_audio_urls``、
          ``reference_audio_bytes_list``。三者互斥于首帧/首尾帧场景。

        样片两步流程：传 ``kwargs["draft_task_id"]`` 时基于样片出正式片；
        传 ``kwargs["draft"]=True`` 时先出样片（仅 480p）。
        """
        kwargs["duration"] = duration
        frame_mode = kwargs.pop("frame_mode", "first")
        kwargs["_frame_mode"] = frame_mode

        model_id = kwargs.get("model_id") or self.config.get("model_id", DEFAULT_MODEL)
        content: list[dict[str, Any]] = []
        if prompt:
            content.append({"type": "text", "text": prompt})

        has_multimodal = any(
            kwargs.get(k)
            for k in (
                "reference_video_urls",
                "reference_audio_urls",
                "reference_audio_bytes_list",
                "reference_image_bytes_list",
            )
        )
        # 全模态参考：图片也按 reference_image 传入，与视频/音频同批
        if frame_mode == "reference" and has_multimodal:
            content.extend(self._build_multimodal_content(image_bytes, kwargs, model_id))
        elif frame_mode == "first_last":
            last_image_bytes = kwargs.pop("last_image_bytes", None)
            if not last_image_bytes:
                raise ProviderError(
                    "Seedance 首尾帧模式需要 last_image_bytes（尾帧图片），"
                    "当前未提供"
                )
            content.append(_build_content("image_url", _to_image_data_url(image_bytes), "first_frame"))
            content.append(_build_content("image_url", _to_image_data_url(last_image_bytes), "last_frame"))
        elif frame_mode == "reference":
            # 单图退化为 reference_image，便于与多图模式统一入口
            ref_list = kwargs.pop("reference_image_bytes_list", None)
            images = ref_list or ([image_bytes] if image_bytes else [])
            for img in images[: _ref_caps(model_id)["image"]]:
                if isinstance(img, bytes) and img:
                    content.append(_build_content("image_url", _to_image_data_url(img), "reference_image"))
            if content:
                kwargs.setdefault("omni_reference_task_type", "reference")
        else:
            # 默认首帧模式，官方文档说明 role 可省略
            if not image_bytes:
                raise ProviderError("Seedance 图生视频缺少输入图片")
            content.append(_build_content("image_url", _to_image_data_url(image_bytes)))

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
        resp = await get_async_client().get(url, headers=self._headers(), timeout=15)
        if resp.status_code == 200:
            return True
        raise ProviderError(f"Seedance 返回 {resp.status_code}: {resp.text[:200]}")
