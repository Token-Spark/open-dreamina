"""Provider 抽象基类与结果数据类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """Provider 调用失败时抛出。"""


@dataclass
class GenerationResult:
    """Provider 生成结果。"""
    file_bytes: bytes
    mime_type: str  # image/png, video/mp4 ...
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """所有 AIGC Provider 的抽象基类。

    子类构造函数应接受 (base_url, api_key, config: dict) 三参数，
    以便 ProviderFactory 通用实例化。
    """

    # 子类可覆盖：该 Provider 支持的生成类型
    SUPPORTED_TYPES: list[str] = []

    @abstractmethod
    async def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        **kwargs: Any,
    ) -> GenerationResult:
        ...

    @abstractmethod
    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        ...

    @abstractmethod
    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        ...

    @abstractmethod
    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """测试 API Key 是否有效。"""
        ...

    @property
    def supported_types(self) -> list[str]:
        return list(self.SUPPORTED_TYPES)
