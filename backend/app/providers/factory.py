"""Provider 工厂。

- 通过 slug 实例化对应 Provider。
- 注册表声明式配置：slug -> (class, default_base_url)
- 新增 Provider 只需在此处注册一行。
"""
from __future__ import annotations

from typing import Any, Callable

from .base import BaseProvider, ProviderError
from .dashscope import DashScopeProvider
from .kling import KlingProvider
from .mock import MockProvider
from .openai_provider import OpenAIProvider
from .stability import StabilityProvider

# 注册表：slug -> (工厂函数, 默认 base_url, 是否内置免 Key)
# 工厂函数签名: (base_url, api_key, config) -> BaseProvider
ProviderFactoryFn = Callable[[str, str, dict[str, Any]], BaseProvider]

_REGISTRY: dict[str, tuple[ProviderFactoryFn, str, bool]] = {
    "mock": (lambda b, k, c: MockProvider(b or "mock://local", k or "mock-key", c), "mock://local", True),
    "stability": (lambda b, k, c: StabilityProvider(b or "https://api.stability.ai", k, c), "https://api.stability.ai", False),
    "openai": (lambda b, k, c: OpenAIProvider(b or "https://api.openai.com/v1", k, c), "https://api.openai.com/v1", False),
    "dashscope": (lambda b, k, c: DashScopeProvider(b or "https://dashscope.aliyuncs.com", k, c), "https://dashscope.aliyuncs.com", False),
    "kling": (lambda b, k, c: KlingProvider(b or "https://api.klingai.com", k, c), "https://api.klingai.com", False),
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
        factory, default_base_url, _built_in = entry
        return factory(base_url or default_base_url, api_key, config or {})

    @staticmethod
    def list_slugs() -> list[str]:
        return list(_REGISTRY.keys())

    @staticmethod
    def is_builtin(slug: str) -> bool:
        entry = _REGISTRY.get(slug)
        return bool(entry and entry[2])

    @staticmethod
    def register(
        slug: str,
        factory: ProviderFactoryFn,
        default_base_url: str,
        builtin: bool = False,
    ) -> None:
        """运行时注册新 Provider（用于插件式扩展）。"""
        _REGISTRY[slug] = (factory, default_base_url, builtin)


def get_provider(
    slug: str,
    base_url: str | None = None,
    api_key: str = "",
    config: dict[str, Any] | None = None,
) -> BaseProvider:
    """便捷函数：等价于 ProviderFactory.get。"""
    return ProviderFactory.get(slug, base_url, api_key, config)
