"""Provider 抽象基类与结果数据类。"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx


class ProviderError(RuntimeError):
    """Provider 调用失败时抛出。

    submit_id：异步任务型 Provider（如本地 CLI）在任务已提交后失败时，
    携带上游任务 ID，供 worker 落库以便 retry 时断点续查、避免重复扣费。
    """

    def __init__(self, message: str, submit_id: str | None = None) -> None:
        super().__init__(message)
        self.submit_id = submit_id


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

    # 上游瞬时故障（5xx / 超时 / 连接错误）自动重试配置；4xx 不重试。
    _MAX_RETRIES = 2  # 首次 + 重试 2 次 = 最多 3 次请求
    _RETRY_BASE_DELAY = 1.5  # 指数退避基数（秒）：1.5s, 3s

    @staticmethod
    def _is_transient(resp: httpx.Response | None, exc: BaseException | None) -> bool:
        """是否为可重试的瞬时故障：网络异常或上游 5xx。4xx 视为客户端错误不重试。"""
        if exc is not None:
            return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))
        return resp is not None and resp.status_code >= 500

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        provider_name: str,
        **request_kwargs: Any,
    ) -> httpx.Response:
        """执行 HTTP 请求并对瞬时故障做有限次指数退避重试；返回的一定是 200 响应，否则抛 ProviderError。

        - 200：直接返回。
        - 4xx：客户端错误，重试无意义，立即抛出。
        - 5xx / 网络异常（超时、连接错误）：记录后按指数退避重试；重试耗尽抛出最后一次错误
          （错误信息中包含上游响应体，火山等服务会在其中带 Request ID，便于提工单查服务端日志）。
        """
        last_resp: httpx.Response | None = None
        last_exc: BaseException | None = None
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                resp = await client.request(method, url, **request_kwargs)
                last_resp = resp
                last_exc = None
                if resp.status_code == 200:
                    return resp
                # 4xx：客户端错误，重试无意义，立即抛出
                if not self._is_transient(resp, None):
                    raise ProviderError(f"{provider_name} 返回 {resp.status_code}: {resp.text}")
                # 5xx：记录后重试（若已是最后一次则在循环外抛出）
            except ProviderError:
                raise
            except httpx.HTTPError as e:
                # 超时 / 连接错误：记录后重试
                last_exc = e
                last_resp = None
            # 最后一次不再等待
            if attempt == self._MAX_RETRIES:
                break
            await asyncio.sleep(self._RETRY_BASE_DELAY * (2 ** attempt))

        # 重试耗尽：用最后一次的错误信息抛出
        if last_resp is not None:
            raise ProviderError(f"{provider_name} 返回 {last_resp.status_code}: {last_resp.text}")
        raise ProviderError(f"{provider_name} 请求失败: {type(last_exc).__name__}: {last_exc}")

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
