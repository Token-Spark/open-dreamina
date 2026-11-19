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

"""快手·可灵 Provider（Kling 4.0 / 4.0 Flash 新版 API 标准）。

新版 API（文档：https://klingai.com/document-api/api/video/4-0/text-to-video）：
- 域名 https://api-beijing.klingai.com，Bearer API Key 鉴权（旧版 AK/SK JWT 已不适用）；
- 版本号在 URL path 中（``/text-to-video/kling-4.0``、``/omni-video/kling-4.0-flash``），
  请求体没有 model 字段；
- 多模态素材统一放 ``contents[]``，每项带 ``id``，在 prompt 中用 ``@id`` 引用；
- 任务异步：POST 创建 → ``GET /tasks?task_ids=`` 轮询 → outputs[].url 下载。

支持：
- 文生视频 / 图生视频（首/中/尾多关键帧）；
- 全能参考（refer_image / feature_video / base_video / element / voice）；
- 主体（element）与音色（voice）的创建、查询、删除。
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx

from .base import BaseProvider, GenerationResult, ProviderError
from ..utils.http_client import get_async_client

logger = logging.getLogger(__name__)

# 默认域名：文档明确新系统由 api.klingai.com 迁移到 api-beijing.klingai.com
KLING_DEFAULT_BASE_URL = "https://api-beijing.klingai.com"

# 版本标识（对应 URL path 末段），不是请求体里的 model 字段
MODEL_KLING_4_0 = "kling-4.0"
MODEL_KLING_4_0_FLASH = "kling-4.0-flash"
DEFAULT_MODEL = MODEL_KLING_4_0

# 版本能力：分辨率 / 时长 / 全能参考素材上限
# 来源：https://klingai.com/document-api/guides/capability-map/video
_MODEL_CAPS: dict[str, dict[str, Any]] = {
    MODEL_KLING_4_0: {
        "resolutions": ("720p", "1080p"),
        "duration": (3, 30),
        "max_images": 10,
        "max_videos": 5,
        "max_elements": 7,
        "max_voices": 3,
        "total_refs": 15,  # 图片 + 视频 + 主体 + 音色
        "supports_voice": True,
        "supports_multi_keyframe": True,
    },
    MODEL_KLING_4_0_FLASH: {
        "resolutions": ("720p",),
        "duration": (3, 20),
        "max_images": 10,
        "max_videos": 5,
        "max_elements": 7,
        "max_voices": 0,  # 能力地图：Flash 不支持音色参考
        "total_refs": 15,
        "supports_voice": False,
        "supports_multi_keyframe": False,
    },
}

# 前端 2160p / 4k 档位在可灵侧收敛到 1080p（4.0 支持 4K 出片，但 settings.resolution
# 的合法值只有 720p/1080p，4K 由套餐/开关决定，这里不误传）。
_RESOLUTION_MAP = {"2160p": "1080p", "4k": "1080p", "720p": "720p", "1080p": "1080p"}
# 前端 auto 比例 → 可灵全能参考的 adaptive；文生/图生视频无 adaptive，回落 16:9
_RATIO_MAP = {
    "auto": "adaptive",
    "adaptive": "adaptive",
    "21:9": "21:9",
    "16:9": "16:9",
    "9:16": "9:16",
    "1:1": "1:1",
    "4:3": "4:3",
    "3:4": "3:4",
}

# 任务终态（新版 API 用 succeeded；主体/音色任务用 succeed，两者都纳入）
_TERMINAL_STATUS = {"succeeded", "succeed", "failed"}
_SUCCESS_STATUS = {"succeeded", "succeed"}


def _normalize_model(model_id: str | None) -> str:
    """把各种 4.0 写法归一到 path 版本标识。"""
    mid = (model_id or "").lower()
    if "flash" in mid:
        return MODEL_KLING_4_0_FLASH
    if "4_0" in mid or "4-0" in mid or "4.0" in mid:
        return MODEL_KLING_4_0
    return MODEL_KLING_4_0


def _caps(model_id: str) -> dict[str, Any]:
    return _MODEL_CAPS[_normalize_model(model_id)]


def _ratio_from_size(width: Any, height: Any) -> str:
    """按宽高比就近归入可灵支持的画面比例。"""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        return "adaptive"
    if w <= 0 or h <= 0:
        return "adaptive"
    r = w / h
    candidates = [
        (21 / 9, "21:9"), (16 / 9, "16:9"), (4 / 3, "4:3"),
        (1 / 1, "1:1"), (3 / 4, "3:4"), (9 / 16, "9:16"),
    ]
    return min(candidates, key=lambda c: abs(r - c[0]))[1]


def _detect_image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "image/jpeg"


def _to_image_url(data: bytes) -> str:
    """可灵 contents[].url 支持 URL 或 base64；本地字节用 data URL 形态。"""
    mime = _detect_image_mime(data)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


class KlingProvider(BaseProvider):
    """快手可灵 4.0 / 4.0 Flash 视频生成 Provider。"""

    SUPPORTED_TYPES = ["text2video", "img2video"]

    _POLL_INTERVAL = 5.0
    _POLL_TIMEOUT = 900.0  # 可灵 4.0 长视频（30s）生成较慢，放宽到 15 分钟

    def __init__(
        self,
        base_url: str = KLING_DEFAULT_BASE_URL,
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = (base_url or KLING_DEFAULT_BASE_URL).rstrip("/")
        # 兼容历史配置里填的旧域名
        if "api.klingai.com" in self.base_url and "api-beijing" not in self.base_url:
            self.base_url = self.base_url.replace("api.klingai.com", "api-beijing.klingai.com")
        self.api_key = api_key
        self.config = config or {}

    # ---- 鉴权 / 通用请求 ----
    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("Kling API Key 未配置")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _api(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """请求可灵 API，校验业务码并返回 data。"""
        resp = await self._request_with_retry(
            client,
            method,
            f"{self.base_url}{path}",
            provider_name="Kling",
            timeout=120,
            headers=self._headers(),
            json=json,
            params=params,
        )
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError(f"Kling 返回非 JSON：{resp.text[:200]}") from exc
        if not isinstance(body, dict):
            raise ProviderError(f"Kling 返回结构异常：{body}")
        code = body.get("code", 0)
        if code not in (0, "0", None):
            raise ProviderError(
                f"Kling 业务错误 code={code}: {body.get('message') or resp.text[:200]}"
            )
        data = body.get("data")
        return data if isinstance(data, dict) or isinstance(data, list) else {}

    # ---- 参数构造 ----
    @staticmethod
    def _build_settings(kwargs: dict[str, Any], model_id: str, *, omni: bool) -> dict[str, Any]:
        caps = _caps(model_id)
        settings: dict[str, Any] = {}

        resolution = _RESOLUTION_MAP.get(str(kwargs.get("resolution") or "").lower())
        if resolution is None:
            # 未显式给出档位时按前端宽高近似选 720p / 1080p
            height = kwargs.get("height")
            try:
                resolution = "1080p" if int(height or 0) > 800 else "720p"
            except (TypeError, ValueError):
                resolution = caps["resolutions"][-1]
        if resolution not in caps["resolutions"]:
            resolution = caps["resolutions"][-1]
        settings["resolution"] = resolution

        ratio_raw = str(kwargs.get("aspect_ratio") or kwargs.get("ratio") or "").lower()
        if ratio_raw:
            ratio = _RATIO_MAP.get(ratio_raw, "16:9")
        else:
            # MCP 路径把 aspect_ratio 换算成 width/height 后不再透传，按宽高反推
            width = kwargs.get("width")
            height = kwargs.get("height")
            ratio = _ratio_from_size(width, height) if width and height else "adaptive"
        if not omni and ratio == "adaptive":
            ratio = "16:9"
        settings["aspect_ratio"] = ratio

        duration = kwargs.get("duration")
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = 0
        lo, hi = caps["duration"]
        # 越界（含未提供/解析失败）时省略 duration，由可灵按 prompt 或默认 10s 决定
        if lo <= duration <= hi:
            settings["duration"] = duration

        if omni:
            audio = str(kwargs.get("audio") or kwargs.get("kling_audio") or "native").lower()
            if audio not in ("native", "original"):
                audio = "native"
            settings["audio"] = audio
        return settings

    @staticmethod
    def _build_options(kwargs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        options: dict[str, Any] = {}
        callback = kwargs.get("callback_url") or config.get("callback_url")
        if callback:
            options["callback_url"] = callback
        external = kwargs.get("external_task_id")
        if external:
            options["external_task_id"] = external
        watermark = kwargs.get("watermark")
        if watermark is None:
            watermark = bool(config.get("watermark", False))
        options["watermark_info"] = {"enabled": bool(watermark)}
        return options

    @staticmethod
    def _assign_id(items: list[dict[str, Any]], prefix: str, start: int = 1) -> int:
        """给 contents 元素编号（@id 引用），返回下一个可用序号。"""
        for i, item in enumerate(items, start=start):
            item.setdefault("id", f"{prefix}_{i}")
        return start + len(items)

    @staticmethod
    def _rewrite_mentions(prompt: str, refs: list[dict[str, Any]]) -> str:
        """把前端 ``@{素材名}`` token 按出现顺序替换为可灵的 ``@id``。

        前端提示词里的 @ 引用以素材名标注（见 usePromptMention），可灵要求用 contents[]
        中定义的 id。按「第 n 个 @token → 第 n 个带 id 的素材」映射；数量不匹配时保留原文
        由模型自行推断（文档允许仅放素材不说明用途）。
        """
        if not prompt or "@{" not in prompt:
            return prompt
        import re

        ids = [r["id"] for r in refs if r.get("id")]
        it = iter(ids)

        def repl(_match: re.Match[str]) -> str:
            ref_id = next(it, None)
            return f"@{ref_id}" if ref_id else ""

        return re.sub(r"@\{[^}]*\}", repl, prompt)

    def _build_image_to_video_contents(
        self,
        prompt: str,
        image_bytes: bytes,
        kwargs: dict[str, Any],
        model_id: str,
    ) -> list[dict[str, Any]]:
        """图生视频：首帧 + 可选中间帧 + 尾帧（4.0 支持多关键帧，Flash 仅首帧）。"""
        caps = _caps(model_id)
        contents: list[dict[str, Any]] = []
        if prompt:
            contents.append({"type": "prompt", "text": prompt})

        frame_mode = kwargs.get("frame_mode") or "first"
        first_items: list[dict[str, Any]] = []
        if image_bytes:
            first_items.append({"type": "first_frame", "url": _to_image_url(image_bytes)})

        middle_items: list[dict[str, Any]] = []
        for raw in kwargs.get("middle_image_bytes_list") or []:
            if isinstance(raw, bytes) and raw:
                middle_items.append({"type": "middle_frame", "url": _to_image_url(raw)})
        if not caps["supports_multi_keyframe"]:
            middle_items = []

        last_items: list[dict[str, Any]] = []
        if frame_mode == "first_last":
            last = kwargs.get("last_image_bytes")
            if not last:
                raise ProviderError("可灵首尾帧模式需要 last_image_bytes（尾帧图片），当前未提供")
            last_items.append({"type": "last_frame", "url": _to_image_url(last)})

        n = self._assign_id(first_items, "frame")
        n = self._assign_id(middle_items, "frame", n)
        self._assign_id(last_items, "frame", n)

        # 按 first / middle / last 顺序排列（文档要求），prompt 保持最前
        contents.extend(first_items)
        contents.extend(middle_items)
        contents.extend(last_items)
        return contents

    def _build_omni_contents(
        self,
        prompt: str,
        image_bytes: bytes,
        kwargs: dict[str, Any],
        model_id: str,
    ) -> list[dict[str, Any]]:
        """全能参考：图片 / 视频 / 主体 / 音色，全部带 id 供 prompt @ 引用。"""
        caps = _caps(model_id)
        contents: list[dict[str, Any]] = []

        # 首帧（若有）→ refer_image（其余图片），按顺序编号
        images: list[dict[str, Any]] = []
        if image_bytes:
            images.append({"type": "first_frame", "url": _to_image_url(image_bytes)})
        for raw in kwargs.get("reference_image_bytes_list") or []:
            if not isinstance(raw, bytes) or not raw:
                continue
            # worker 的参考列表含首图，跳过与 image_bytes 相同的那张，避免重复引用
            if image_bytes and raw == image_bytes:
                continue
            images.append({"type": "refer_image", "url": _to_image_url(raw)})
        for url in kwargs.get("reference_image_urls") or []:
            if isinstance(url, str) and url:
                images.append({"type": "refer_image", "url": url})
        images = images[: caps["max_images"]]
        n = self._assign_id(images, "image")

        videos: list[dict[str, Any]] = []
        for url in kwargs.get("reference_video_urls") or []:
            if isinstance(url, str) and url:
                videos.append({"type": "feature_video", "url": url})
        for url in kwargs.get("base_video_urls") or []:
            if isinstance(url, str) and url:
                videos.append({"type": "base_video", "url": url})
        videos = videos[: caps["max_videos"]]
        n = self._assign_id(videos, "video", n)

        elements: list[dict[str, Any]] = []
        for eid in kwargs.get("element_ids") or []:
            if isinstance(eid, str) and eid:
                elements.append({"type": "element", "element_id": eid})
        elements = elements[: caps["max_elements"]]
        n = self._assign_id(elements, "element", n)

        voices: list[dict[str, Any]] = []
        if caps["supports_voice"]:
            for vid in kwargs.get("voice_ids") or []:
                if isinstance(vid, str) and vid:
                    voices.append({"type": "voice", "voice_id": vid})
            voices = voices[: caps["max_voices"]]
        n = self._assign_id(voices, "voice", n)

        refs = images + videos + elements + voices
        if len(refs) > caps["total_refs"]:
            raise ProviderError(
                f"可灵全能参考素材总数上限 {caps['total_refs']}，当前 {len(refs)}，请减少参考素材"
            )

        rewritten = self._rewrite_mentions(prompt, refs)
        if rewritten:
            contents.append({"type": "prompt", "text": rewritten})
        contents.extend(refs)
        return contents

    # ---- 任务创建 / 轮询 ----
    async def _create_and_wait(
        self,
        endpoint: str,
        payload: dict[str, Any],
        submit_id: str | None,
    ) -> dict[str, Any]:
        client = get_async_client()
        if submit_id:
            task_id = submit_id
            logger.info("Kling 断点续查: task_id=%s", task_id)
        else:
            data = await self._api(client, "POST", endpoint, json=payload)
            task_id = str(data.get("id") or data.get("task_id") or "")
            if not task_id:
                raise ProviderError(f"Kling 创建任务未返回 id：{data}")
        return await self._poll_task(client, task_id)

    async def _poll_task(self, client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
        elapsed = 0.0
        while elapsed < self._POLL_TIMEOUT:
            data = await self._api(
                client, "GET", "/tasks", params={"task_ids": task_id}
            )
            # 新版查询返回 data 数组
            task: dict[str, Any] = {}
            if isinstance(data, list) and data:
                task = data[0] if isinstance(data[0], dict) else {}
            elif isinstance(data, dict):
                result = data.get("result") or data.get("tasks") or []
                if isinstance(result, list) and result:
                    task = result[0] if isinstance(result[0], dict) else {}
            status = str(task.get("status") or "").lower()
            if status in _TERMINAL_STATUS:
                if status not in _SUCCESS_STATUS:
                    raise ProviderError(
                        f"Kling 任务 {task_id} 失败：{task.get('message') or task}"
                    )
                return task
            await asyncio.sleep(self._POLL_INTERVAL)
            elapsed += self._POLL_INTERVAL
        raise ProviderError(
            f"Kling 任务 {task_id} 轮询超时（>{int(self._POLL_TIMEOUT)}s）。"
            "重试将从已有任务断点续查，不会重复提交",
            submit_id=task_id,
        )

    async def _finish(self, task: dict[str, Any], model_id: str) -> GenerationResult:
        outputs = task.get("outputs")
        video_url = ""
        if isinstance(outputs, list):
            for out in outputs:
                if isinstance(out, dict) and out.get("type") == "video" and out.get("url"):
                    video_url = str(out["url"])
                    break
        if not video_url:
            raise ProviderError(f"Kling 任务成功但未返回视频 URL：{task}")
        resp = await self._request_with_retry(
            get_async_client(), "GET", video_url, provider_name="Kling 视频下载", timeout=180
        )
        metadata: dict[str, Any] = {
            "model": model_id,
            "task_id": str(task.get("id") or ""),
            "kling_task_status": task.get("status"),
        }
        usage = task.get("usage")
        if isinstance(usage, dict):
            for k in ("input_duration", "output_duration"):
                if k in usage:
                    metadata[k] = usage[k]
        return GenerationResult(
            file_bytes=resp.content, mime_type="video/mp4", metadata=metadata
        )

    # ---- BaseProvider 接口 ----
    async def text_to_video(
        self, prompt: str, duration: int = 5, **kwargs: Any
    ) -> GenerationResult:
        kwargs["duration"] = duration
        model_id = str(kwargs.get("model_id") or self.config.get("model_id") or DEFAULT_MODEL)
        version = _normalize_model(model_id)
        has_refs = any(
            kwargs.get(k)
            for k in (
                "reference_image_urls", "reference_video_urls", "base_video_urls",
                "element_ids", "voice_ids", "reference_image_bytes_list",
            )
        )
        if has_refs:
            # 文本 + 多模态参考：走全能参考接口
            contents = self._build_omni_contents(prompt, b"", kwargs, model_id)
            endpoint = f"/omni-video/{version}"
        else:
            contents = [{"type": "prompt", "text": prompt}] if prompt else []
            endpoint = f"/text-to-video/{version}"

        payload = {
            "contents" if has_refs else "prompt": contents if has_refs else prompt,
            "settings": self._build_settings(kwargs, model_id, omni=has_refs),
            "options": self._build_options(kwargs, self.config),
        }
        task = await self._create_and_wait(
            endpoint, payload, kwargs.get("submit_id")
        )
        return await self._finish(task, model_id)

    async def image_to_video(
        self, image_bytes: bytes, prompt: str = "", duration: int = 5, **kwargs: Any
    ) -> GenerationResult:
        kwargs["duration"] = duration
        model_id = str(kwargs.get("model_id") or self.config.get("model_id") or DEFAULT_MODEL)
        version = _normalize_model(model_id)

        # 全模态：reference 帧模式或带了视频/主体/音色
        has_omni = any(
            kwargs.get(k)
            for k in (
                "reference_video_urls", "base_video_urls", "element_ids", "voice_ids",
                "reference_image_bytes_list", "reference_image_urls",
            )
        ) or kwargs.get("frame_mode") == "reference"
        if has_omni:
            contents = self._build_omni_contents(prompt, image_bytes, kwargs, model_id)
            endpoint = f"/omni-video/{version}"
        else:
            if not image_bytes:
                raise ProviderError("Kling 图生视频缺少输入图片")
            contents = self._build_image_to_video_contents(prompt, image_bytes, kwargs, model_id)
            endpoint = f"/image-to-video/{version}"

        payload = {
            "contents": contents,
            "settings": self._build_settings(kwargs, model_id, omni=has_omni),
            "options": self._build_options(kwargs, self.config),
        }
        task = await self._create_and_wait(endpoint, payload, kwargs.get("submit_id"))
        return await self._finish(task, model_id)

    async def text_to_image(
        self, prompt: str, negative_prompt: str = "", width: int = 1024,
        height: int = 1024, steps: int = 30, **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Kling Provider 当前不支持 text_to_image")

    async def image_to_image(
        self, image_bytes: list[bytes], prompt: str, strength: float = 0.7, **kwargs: Any
    ) -> GenerationResult:
        raise ProviderError("Kling Provider 当前不支持 image_to_image")

    async def test_connection(self) -> bool:
        if not self.api_key:
            raise ProviderError("Kling API Key 未配置")
        # 用主体列表（GET）做连通性探测，不消耗生成额度
        await self._api(get_async_client(), "GET", "/v1/general/advanced-presets-elements",
                        params={"pageNum": 1, "pageSize": 1})
        return True

    # ---- 主体（element）管理 ----
    async def create_element(
        self,
        element_name: str,
        element_description: str,
        reference_type: str,
        *,
        frontal_image_url: str | None = None,
        refer_image_urls: list[str] | None = None,
        refer_video_url: str | None = None,
        element_voice_id: str | None = None,
        tag_ids: list[str] | None = None,
        external_task_id: str | None = None,
    ) -> str:
        """创建主体，返回任务 ID；用 get_element(task_id) 轮询取 element_id。"""
        if reference_type not in ("image_refer", "video_refer"):
            raise ProviderError("reference_type 只能是 image_refer / video_refer")
        body: dict[str, Any] = {
            "element_name": element_name,
            "element_description": element_description,
            "reference_type": reference_type,
        }
        if reference_type == "image_refer":
            if not frontal_image_url:
                raise ProviderError("image_refer 主体需要 frontal_image_url（正面参考图）")
            body["element_image_list"] = {
                "frontal_image": frontal_image_url,
                "refer_images": [{"image_url": u} for u in (refer_image_urls or []) if u],
            }
        else:
            if not refer_video_url:
                raise ProviderError("video_refer 主体需要 refer_video_url（参考视频）")
            body["element_video_list"] = {"refer_videos": [{"video_url": refer_video_url}]}
        if element_voice_id:
            body["element_voice_id"] = element_voice_id
        if tag_ids:
            body["tag_list"] = [{"tag_id": t} for t in tag_ids]
        if external_task_id:
            body["external_task_id"] = external_task_id
        data = await self._api(
            get_async_client(), "POST", "/v1/general/advanced-custom-elements", json=body
        )
        task_id = str(data.get("task_id") or "")
        if not task_id:
            raise ProviderError(f"Kling 创建主体未返回 task_id：{data}")
        return task_id

    async def get_element(self, element_task_id: str) -> dict[str, Any]:
        data = await self._api(
            get_async_client(),
            "GET",
            f"/v1/general/advanced-custom-elements/{element_task_id}",
        )
        return data if isinstance(data, dict) else {}

    async def list_elements(self, page_num: int = 1, page_size: int = 30) -> list[dict[str, Any]]:
        data = await self._api(
            get_async_client(),
            "GET",
            "/v1/general/advanced-custom-elements",
            params={"pageNum": page_num, "pageSize": page_size},
        )
        return data if isinstance(data, list) else []

    async def delete_element(self, element_id: str) -> dict[str, Any]:
        return await self._api(
            get_async_client(),
            "POST",
            "/v1/general/delete-advanced-elements",
            json={"element_id": element_id},
        )

    # ---- 音色（voice）管理 ----
    async def create_voice(
        self, voice_name: str, *, voice_url: str | None = None,
        video_id: str | None = None, external_task_id: str | None = None,
    ) -> str:
        if bool(voice_url) == bool(video_id):
            raise ProviderError("voice_url 与 video_id 必须且只能传一个")
        body: dict[str, Any] = {"voice_name": voice_name}
        if voice_url:
            body["voice_url"] = voice_url
        if video_id:
            body["video_id"] = video_id
        if external_task_id:
            body["external_task_id"] = external_task_id
        data = await self._api(
            get_async_client(), "POST", "/v1/general/custom-voices", json=body
        )
        task_id = str(data.get("task_id") or "")
        if not task_id:
            raise ProviderError(f"Kling 创建音色未返回 task_id：{data}")
        return task_id

    async def get_voice(self, voice_task_id: str) -> dict[str, Any]:
        data = await self._api(
            get_async_client(), "GET", f"/v1/general/custom-voices/{voice_task_id}"
        )
        return data if isinstance(data, dict) else {}

    async def list_voices(self, page_num: int = 1, page_size: int = 30) -> list[dict[str, Any]]:
        data = await self._api(
            get_async_client(), "GET", "/v1/general/custom-voices",
            params={"pageNum": page_num, "pageSize": page_size},
        )
        return data if isinstance(data, list) else []

    async def delete_voice(self, voice_id: str) -> dict[str, Any]:
        return await self._api(
            get_async_client(), "POST", "/v1/general/delete-voices",
            json={"voice_id": voice_id},
        )
