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

"""Spark Hub Seedance 生视频 Provider。

对接 Spark Hub 中转站的 Seedance 生视频模型（api_name：doubao_seedance_2、
doubao_seedance_2_fast/mini、doubao_seedance_2_5 等）。
异步任务模式，返回 result.videos[]（视频 URL 数组）。
各型号分辨率限制用配置表表达（doubao_seedance_2 支持 4K，fast/mini/2.5 仅 480p/720p）。

Seedance 2.5 额外支持：多模态参考（image_urls[]/video_urls[]/audio_urls[]）、
首帧/尾帧（first_image_url/last_image_url，此时 aspect_ratio 必须为 adaptive）、
生成同步音频（kwargs.generate_audio）。
"""
from __future__ import annotations

from typing import Any

from .base import GenerationResult, ProviderError
from .sparkhub_base import SparkHubBaseProvider, _find

# (width, height) -> (resolution, ratio) 反查表，与前端 VIDEO_SIZE_TABLE 对齐。
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

# 分辨率档位映射：2160p 视为 4K 别名。
_RESOLUTION_ALIAS = {"2160p": "2160p", "4k": "2160p"}

# 各型号允许的分辨率档位（最多 4K 或 720p）。
_MODEL_MAX_RESOLUTION: dict[str, str] = {
    "doubao_seedance_2": "2160p",        # 480p/720p/1080p/2160p(4K)
    "doubao_seedance_2_fast": "720p",    # 仅 480p/720p
    "doubao_seedance_2_mini": "720p",    # 仅 480p/720p
    "doubao_seedance_2_5": "720p",       # 仅 480p/720p
}

# 多模态参考素材的类型与最大数量（Seedance 2.5；总数上限 50，图 30/视频 10/音频 10）。
_REF_URL_KEYS: dict[str, int] = {
    "image_urls": 30,
    "video_urls": 10,
    "audio_urls": 10,
}


def _aspect_ratio_from_size(width: int, height: int) -> str:
    """按宽高比就近归入 Seedance 支持的画面比例。"""
    if width <= 0 or height <= 0:
        return "adaptive"  # Spark Hub 默认自适应
    ratio = width / height
    candidates = [
        (21 / 9, "21:9"),
        (16 / 9, "16:9"),
        (4 / 3, "4:3"),
        (1 / 1, "1:1"),
        (3 / 4, "3:4"),
        (9 / 16, "9:16"),
    ]
    return min(candidates, key=lambda c: abs(ratio - c[0]))[1]


class SparkHubSeedanceProvider(SparkHubBaseProvider):
    SUPPORTED_TYPES = ["text2video", "img2video"]

    def _build_create_payload(self, prompt: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        api_name = kwargs.get("model_id") or self.config.get("model_id")
        if not api_name:
            raise ProviderError("Spark Hub Seedance 未配置 api_name（模型 ID）")
        width = int(kwargs.get("width") or 0)
        height = int(kwargs.get("height") or 0)
        resolution, ratio = _VIDEO_SIZE_REVERSE.get((width, height), (None, None))
        if not resolution:
            resolution = "720p"
            ratio = _aspect_ratio_from_size(width, height)
        # 首帧/尾帧任务仅支持 aspect_ratio=adaptive（Seedance 2.5 约束）
        if kwargs.get("first_image_url") or kwargs.get("last_image_url"):
            ratio = "adaptive"
        # 校验当前 api_name 允许的分辨率档位
        max_res = _MODEL_MAX_RESOLUTION.get(api_name, "2160p")
        if resolution in _RESOLUTION_ALIAS:
            resolution = _RESOLUTION_ALIAS[resolution]
        if resolution != "2160p" and max_res == "720p" and resolution not in ("480p", "720p"):
            raise ProviderError(
                f"模型 {api_name} 不支持 {resolution}，仅支持 480p / 720p，请降低分辨率"
            )

        duration = int(kwargs.get("duration") or 5)
        pl: dict[str, Any] = {
            "api_name": api_name,
            "prompt": prompt,
            "resolution": resolution,
            "aspect_ratio": ratio,
            "duration": duration,
        }
        # 多模态参考素材（公网 URL 或审核后 asset:// 地址）：图/视频/音频，按类型限量
        for key, cap in _REF_URL_KEYS.items():
            urls = kwargs.get(key)
            if isinstance(urls, list):
                cleaned = [u for u in urls if isinstance(u, str) and u][:cap]
                if cleaned:
                    pl[key] = cleaned
        # 首帧 / 尾帧图（尾帧必须与首帧同时使用，交由上游校验）
        for key in ("first_image_url", "last_image_url"):
            url = kwargs.get(key)
            if isinstance(url, str) and url:
                pl[key] = url
        # 是否生成配音音效（默认 true；false 生成无声视频）
        generate_audio = kwargs.get("generate_audio")
        if generate_audio is not None:
            pl.setdefault("kwargs", {})["generate_audio"] = bool(generate_audio)
        return pl

    def _extract_result_urls(self, polled: dict[str, Any]) -> list[str]:
        videos = _find(polled, "videos")
        if isinstance(videos, dict):
            videos = videos.get("videos")
        if not isinstance(videos, list):
            return []
        return [u for u in videos if isinstance(u, str) and u]

    def _result_mime(self) -> str:
        return "video/mp4"

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        payload = self._build_create_payload(prompt, kwargs)
        return await self._run_task(payload, self._extract_result_urls, self._result_mime())

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        # Spark Hub 生视频支持首帧/尾帧（first_image_url/last_image_url，aspect_ratio 强制 adaptive）、
        # 多模态参考（image_urls[]/video_urls[]/audio_urls[]），均需公网 URL 或审核后 asset:// 地址。
        # 本地资产无公网 URL，且素材提审本期未接入，因此图片输入走 URL 需由调用方提供。
        has_ref = any(
            kwargs.get(k)
            for k in ("first_image_url", "last_image_url", "image_url", "image_urls", "video_urls", "audio_urls")
        )
        if not has_ref:
            raise ProviderError(
                "Spark Hub Seedance 图生视频需要参考素材的公网链接"
                "（first_image_url / image_urls / video_urls / audio_urls），"
                "当前本地资产暂不支持，请选择文生视频，或提供公网参考素材 URL"
            )
        payload = self._build_create_payload(prompt, kwargs)
        # 兼容旧入口 image_url：归入多模态 image_urls（first_image_url 由 _build_create_payload 顶层处理）
        legacy_url = kwargs.get("image_url")
        if legacy_url and not kwargs.get("image_urls"):
            payload.setdefault("image_urls", []).append(legacy_url)
        return await self._run_task(payload, self._extract_result_urls, self._result_mime())

    async def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Spark Hub Seedance 不支持 text_to_image")

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("Spark Hub Seedance 不支持 image_to_image")
