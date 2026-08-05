"""AIGC Provider 适配层（策略 + 工厂模式）。"""
from .base import BaseProvider, GenerationResult, ProviderError
from .factory import ProviderFactory, get_provider

__all__ = [
    "BaseProvider",
    "GenerationResult",
    "ProviderError",
    "ProviderFactory",
    "get_provider",
]
