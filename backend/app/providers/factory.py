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

"""Provider 工厂。

- 通过 slug 实例化对应 Provider。
- 注册表声明式配置：slug -> RegistryEntry
- 新增 Provider 只需在此处注册一行。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .base import BaseProvider, ProviderError
from .dashscope_provider import DashScopeProvider
from .dreamina_cli_provider import DreaminaSeedanceProvider, DreaminaSeedreamProvider
from .gemini_image_provider import GeminiImageProvider
from .kling_provider import KlingProvider
from .mock_provider import MockProvider
from .openai_provider import OpenAIProvider
from .seedance_provider import MODEL_SEEDANCE_2_0, MODEL_SEEDANCE_2_5, SeedanceProvider
from .seedream_provider import SeedreamProvider
from .sparkhub_seedance import SparkHubSeedanceProvider
from .sparkhub_seedream import SparkHubSeedreamProvider
from .stability_provider import StabilityProvider

# 工厂函数签名: (base_url, api_key, config) -> BaseProvider
ProviderFactoryFn = Callable[[str, str, dict[str, Any]], BaseProvider]

# 内容模式与任务类型的映射（与前端 ContentMode 对齐）
_IMAGE_TYPES = {"text2img", "img2img"}
_VIDEO_TYPES = {"text2video", "img2video"}


def _modes_from_types(types: list[str]) -> list[str]:
    """由 SUPPORTED_TYPES 派生内容模式（image/video），数据驱动避免硬编码。"""
    modes: list[str] = []
    if any(t in _IMAGE_TYPES for t in types):
        modes.append("image")
    if any(t in _VIDEO_TYPES for t in types):
        modes.append("video")
    return modes


@dataclass
class RegistryEntry:
    """Provider 注册项：工厂 + 元信息（数据驱动 UI 展示）。"""
    factory: ProviderFactoryFn
    default_base_url: str
    builtin: bool
    display_name: str
    modes: list[str] = field(default_factory=list)
    hidden: bool = False  # 不在前端 slug 下拉中展示（如已拆分的遗留 slug 兼容别名）


_REGISTRY: dict[str, RegistryEntry] = {
    "mock": RegistryEntry(
        factory=lambda b, k, c: MockProvider(b or "mock://local", k or "mock-key", c),
        default_base_url="mock://local",
        builtin=True,
        display_name="Mock（本地测试）",
        modes=_modes_from_types(MockProvider.SUPPORTED_TYPES),
    ),
    "stability": RegistryEntry(
        factory=lambda b, k, c: StabilityProvider(b or "https://api.stability.ai", k, c),
        default_base_url="https://api.stability.ai",
        builtin=False,
        display_name="Stability AI",
        modes=_modes_from_types(StabilityProvider.SUPPORTED_TYPES),
    ),
    "openai": RegistryEntry(
        # slug 标识「OpenAI 兼容图片生成接口」，与供应商解耦：
        # 官方 api.openai.com 或 OpenRouter（https://openrouter.ai/api/v1）均可接入，
        # 模型为 GPT Image 2（gpt-image-2）。
        factory=lambda b, k, c: OpenAIProvider(b or "https://api.openai.com/v1", k, c),
        default_base_url="https://api.openai.com/v1",
        builtin=False,
        display_name="OpenAI（GPT Image 2）",
        modes=_modes_from_types(OpenAIProvider.SUPPORTED_TYPES),
    ),
    "gemini-3-pro-image": RegistryEntry(
        # OpenRouter Nano Banana Pro（Gemini 3 Pro Image）；Chat Completions + modalities 协议
        factory=lambda b, k, c: GeminiImageProvider(b or "https://openrouter.ai/api/v1", k, c),
        default_base_url="https://openrouter.ai/api/v1",
        builtin=False,
        display_name="Gemini 3 Pro Image（OpenRouter）",
        modes=_modes_from_types(GeminiImageProvider.SUPPORTED_TYPES),
    ),
    "dashscope": RegistryEntry(
        factory=lambda b, k, c: DashScopeProvider(b or "https://dashscope.aliyuncs.com", k, c),
        default_base_url="https://dashscope.aliyuncs.com",
        builtin=False,
        display_name="阿里云通义万相",
        modes=_modes_from_types(DashScopeProvider.SUPPORTED_TYPES),
    ),
    "kling": RegistryEntry(
        factory=lambda b, k, c: KlingProvider(b or "https://api.klingai.com", k, c),
        default_base_url="https://api.klingai.com",
        builtin=False,
        display_name="快手可灵",
        modes=_modes_from_types(KlingProvider.SUPPORTED_TYPES),
    ),
    "seedream": RegistryEntry(
        factory=lambda b, k, c: SeedreamProvider(b or "https://ark.cn-beijing.volces.com/api/v3", k, c),
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        builtin=False,
        display_name="豆包 Seedream",
        modes=_modes_from_types(SeedreamProvider.SUPPORTED_TYPES),
    ),
    "seedance-2-0": RegistryEntry(
        factory=lambda b, k, c: SeedanceProvider(
            b or "https://ark.cn-beijing.volces.com/api/v3",
            k,
            {**c, "model_id": MODEL_SEEDANCE_2_0},
        ),
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        builtin=False,
        display_name="豆包 Seedance 2.0",
        modes=_modes_from_types(SeedanceProvider.SUPPORTED_TYPES),
    ),
    "seedance-2-5": RegistryEntry(
        factory=lambda b, k, c: SeedanceProvider(
            b or "https://ark.cn-beijing.volces.com/api/v3",
            k,
            {**c, "model_id": MODEL_SEEDANCE_2_5},
        ),
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        builtin=False,
        display_name="豆包 Seedance 2.5",
        modes=_modes_from_types(SeedanceProvider.SUPPORTED_TYPES),
    ),
    "sparkhub-seedream": RegistryEntry(
        # Spark Hub 中转站生图（Seedream）；协议为统一异步任务 + X-API-Key
        factory=lambda b, k, c: SparkHubSeedreamProvider(
            b or "https://operation.spark-hub.cn/task-api", k, c,
        ),
        default_base_url="https://operation.spark-hub.cn/task-api",
        builtin=False,
        display_name="Spark Hub Seedream（中转生图）",
        modes=_modes_from_types(SparkHubSeedreamProvider.SUPPORTED_TYPES),
    ),
    "sparkhub-seedance": RegistryEntry(
        # Spark Hub 中转站生视频（Seedance）；协议为统一异步任务 + X-API-Key
        factory=lambda b, k, c: SparkHubSeedanceProvider(
            b or "https://operation.spark-hub.cn/task-api", k, c,
        ),
        default_base_url="https://operation.spark-hub.cn/task-api",
        builtin=False,
        display_name="Spark Hub Seedance（中转生视频）",
        modes=_modes_from_types(SparkHubSeedanceProvider.SUPPORTED_TYPES),
    ),
    "dreamina-seedance": RegistryEntry(
        # 即梦 CLI 视频侧（Seedance 系列）；base_url 复用为 CLI 可执行路径，api_key 不使用（本机 OAuth 登录态）
        factory=lambda b, k, c: DreaminaSeedanceProvider(b or "dreamina", k, c),
        default_base_url="dreamina",
        builtin=False,
        display_name="即梦 Seedance（CLI 视频）",
        modes=_modes_from_types(DreaminaSeedanceProvider.SUPPORTED_TYPES),
    ),
    "dreamina-seedream": RegistryEntry(
        # 即梦 CLI 图片侧（Seedream / 即梦图片模型）；与视频侧共用同一个 CLI 与登录态
        factory=lambda b, k, c: DreaminaSeedreamProvider(b or "dreamina", k, c),
        default_base_url="dreamina",
        builtin=False,
        display_name="即梦 Seedream（CLI 图片）",
        modes=_modes_from_types(DreaminaSeedreamProvider.SUPPORTED_TYPES),
    ),
    "dreamina-cli": RegistryEntry(
        # 遗留 slug 兼容别名：已拆分为 dreamina-seedance / dreamina-seedream，
        # 仅为存量已配置的 Provider（DB 中 slug=dreamina-cli）继续提供视频生成能力
        factory=lambda b, k, c: DreaminaSeedanceProvider(b or "dreamina", k, c),
        default_base_url="dreamina",
        builtin=False,
        display_name="即梦 CLI（已拆分，请改用 dreamina-seedance / dreamina-seedream）",
        modes=_modes_from_types(DreaminaSeedanceProvider.SUPPORTED_TYPES),
        hidden=True,
    ),
}


class ProviderFactory:
    """Provider 工厂类。"""

    @staticmethod
    def get(
        slug: str,
        base_url: str | None = None,
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> BaseProvider:
        entry = _REGISTRY.get(slug)
        if entry is None:
            raise ProviderError(f"未知 Provider slug: {slug}")
        return entry.factory(base_url or entry.default_base_url, api_key, config or {})

    @staticmethod
    def list_slugs() -> list[str]:
        return list(_REGISTRY.keys())

    @staticmethod
    def is_builtin(slug: str) -> bool:
        entry = _REGISTRY.get(slug)
        return bool(entry and entry.builtin)

    @staticmethod
    def list_slug_info() -> list[dict[str, Any]]:
        """返回所有可用 slug 的元信息，供前端下拉选择（隐藏项除外）。"""
        return [
            {
                "slug": slug,
                "display_name": entry.display_name,
                "modes": list(entry.modes),
                "default_base_url": entry.default_base_url,
                "builtin": entry.builtin,
            }
            for slug, entry in _REGISTRY.items()
            if not entry.hidden
        ]

    @staticmethod
    def register(
        slug: str,
        factory: ProviderFactoryFn,
        default_base_url: str,
        builtin: bool = False,
    ) -> None:
        """运行时注册新 Provider（用于插件式扩展）。"""
        _REGISTRY[slug] = RegistryEntry(
            factory=factory,
            default_base_url=default_base_url,
            builtin=builtin,
            display_name=slug,
            modes=[],
        )


def get_provider(
    slug: str,
    base_url: str | None = None,
    api_key: str = "",
    config: dict[str, Any] | None = None,
) -> BaseProvider:
    """便捷函数：等价于 ProviderFactory.get。"""
    return ProviderFactory.get(slug, base_url, api_key, config)
