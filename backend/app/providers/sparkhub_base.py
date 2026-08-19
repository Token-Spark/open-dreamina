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

"""Spark Hub 中转站 Provider 基类。

对接 Spark Hub 星火社区大模型资源管理平台（https://operation.spark-hub.cn/api-doc）：
生图 / 生视频均为「统一异步任务」模式——创建任务 → 轮询状态 → 下载结果 URL。

本类只承载 Spark Hub 的通用机制（鉴权头、异步任务生命周期、业务错误码映射、
结果下载）；生图 / 生视频的具体入参构造与结果解析由子类完成，体现策略与机制分离。
"""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC
from typing import Any, Callable

import httpx

from .base import BaseProvider, GenerationResult, ProviderError

logger = logging.getLogger(__name__)

# Spark Hub 统一异步任务接口路径
_CREATE_PATH = "/task/create_task"
_QUERY_PATH = "/task/query_task/{task_id}"
_ORIGINAL_PATH = "/task/original_response/{task_id}"

# 业务错误码 → 修复建议（数据驱动，P0.3；码表见 API 文档「错误码对照表」）。
_ERROR_HINTS: dict[int, str] = {
    401: "API Key 缺失或无效，请在设置页检查并修改",
    403: "当前账号无权限访问该资源，请联系 Spark Hub 平台",
    404: "访问的接口或资源不存在，请检查 API 地址与 api_name",
    405: "目标模型当前队列已满，请稍后重试",
    406: "指定调用的模型暂不可用，请更换模型或稍后再试",
    409: "账户余额不足，无法发起任务，请前往 Spark Hub 充值",
    412: "当前账号未开通该模型 API 调用权限，请联系平台开通",
    413: "API Key 所属账号已被停用，请联系平台管理员",
    500: "Spark Hub 服务内部异常，建议稍后重试",
    504: "请求处理超时，建议稍后重试",
}


def _find(data: dict[str, Any], *keys: str) -> Any:
    """深度优先取首个命中的键值（兼容多种字段命名差异）。"""
    for key in keys:
        if not isinstance(data, dict):
            break
        if key in data:
            return data[key]
        for v in data.values():
            if isinstance(v, dict):
                found = _find(v, *keys)
                if found is not None:
                    return found
    return None


# 终态失败原因候选字段：query_task 的失败描述命名不一，且顶层常存在空串
# 占位（如 `"error": ""`），若按原 _find 顺序取首个命中会把真实原因吞掉。
_FAILURE_KEYS = ("message", "error", "error_msg", "err_msg", "fail_reason", "error_code")


def _find_nonempty(data: dict[str, Any], *keys: str) -> Any:
    """深度优先取首个「非空」命中的字段值（跳过 None/空串/纯空白）。"""
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data:
            val = data[key]
            if val is not None and str(val).strip():
                return val
        for v in data.values():
            if isinstance(v, dict):
                found = _find_nonempty(v, key)
                if found is not None:
                    return found
    return None


def _collect_error_parts(payload: dict[str, Any]) -> list[str]:
    """递归收集形如 {"code": ..., "message": ...} 的错误对象文本（原始响应用）。"""
    parts: list[str] = []
    stack: list[Any] = list(payload.values()) if isinstance(payload, dict) else []
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            err = node.get("error")
            if isinstance(err, dict):
                seg = " ".join(
                    str(v) for v in (err.get("code"), err.get("message")) if v and str(v).strip()
                )
                if seg.strip() and seg not in parts:
                    parts.append(seg.strip())
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return parts


# 已知的内容安全失败码片段 → 修复建议（命中即附加，便于用户自助调整）。
_SENSITIVE_CODE_HINTS: tuple[tuple[str, str], ...] = (
    (
        "OutputVideoSensitiveContentDetected",
        "生成结果触发上游内容安全检测（疑似版权/敏感内容限制），"
        "请调整画面内容（避免歌曲演唱、真人肖像、品牌标识等）后重新生成",
    ),
    ("SensitiveContentDetection", "生成结果触发上游内容安全检测，请调整提示词后重新生成"),
)


def _content_hint(reason: str) -> str:
    for code, hint in _SENSITIVE_CODE_HINTS:
        if code in reason:
            return hint
    return ""


def _detect_mime(data: bytes) -> str:
    """按魔数识别常见媒体 MIME；未知回退到 image/png。"""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    if data.startswith(b"\x00\x00\x00") and b"ftyp" in data[4:12]:
        return "video/mp4"
    return "image/png"


class SparkHubBaseProvider(BaseProvider, ABC):
    """Spark Hub 通用机制基类。

    子类需实现：
    - _build_create_payload(prompt, kwargs) -> dict：构造 create_task 请求体
    - _extract_result_urls(polled: dict) -> list[str]：从终态响应提取结果 URL
    - _result_mime() -> str：结果默认 MIME
    """

    SUPPORTED_TYPES: list[str] = []

    # 任务轮询配置
    _POLL_INTERVAL = 5.0
    _POLL_TIMEOUT = 600.0  # 单次生成最长等待（秒）：10 分钟

    # 终态判定：轮询返回体中判为成功的状态集合；失败/其它视为失败。
    # 实测 Spark Hub 生视频/生图成功终态为 "completed"（query_task 的 data.status），
    # 兼容旧写法 "succeeded"/"success"，避免状态不匹配导致轮询永不结束、前端无限等待。
    _SUCCESS_STATUSES = {"succeeded", "completed", "success"}
    _TERMINAL_FAILED = {"failed", "cancelled", "expired"}

    def __init__(
        self,
        base_url: str = "https://operation.spark-hub.cn/task-api",
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip() if api_key else ""
        self.config = config or {}
        # 上游状态变更回调 (status, elapsed_s)，由 worker 注入以把上游进度推给前端；
        # 同步函数，回调异常不应影响主流程（_poll 内已兜底）。
        self.on_status: Callable[[str, float], None] | None = None

    # ---------- HTTP / 业务错误码 ----------

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("Spark Hub API Key 未配置，请在设置页填写")
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _raise_business_error(self, payload: dict[str, Any], context: str) -> None:
        """解析业务响应码，命中已知码表时抛出带修复建议的错误。

        Spark Hub 业务码可能以 HTTP 状态码返回，也可能以 HTTP 200 + 响应体 code 返回，
        这里统一检查响应体 code（Http 状态码由 _request_with_retry 处理）。
        """
        code = _find(payload, "code", "error_code", "status_code")
        if not isinstance(code, int):
            return
        hint = _ERROR_HINTS.get(code)
        message = _find(payload, "message", "error", "msg")
        if hint:
            raise ProviderError(f"{context}失败（code={code}）：{message or ''} {hint}".strip())
        if code != 200:
            raise ProviderError(f"{context}失败（code={code}）：{message or ''}".strip())

    # ---------- 异步任务生命周期 ----------

    async def _submit(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> str:
        """创建异步任务，返回 task_id。"""
        resp = await self._request_with_retry(
            client, "POST", f"{self.base_url}{_CREATE_PATH}",
            provider_name="Spark Hub", headers=self._headers(), json=payload,
        )
        data = resp.json()
        self._raise_business_error(data, "创建任务")
        task_id = _find(data, "task_id", "id", "data")
        if not isinstance(task_id, str) or not task_id:
            raise ProviderError(f"Spark Hub 创建任务未返回 task_id：{data}")
        return task_id

    async def _poll(self, client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
        """轮询任务直到终态；返回终态响应体。"""
        url = f"{self.base_url}{_QUERY_PATH.format(task_id=task_id)}"
        elapsed = 0.0
        last_status = ""
        while elapsed < self._POLL_TIMEOUT:
            resp = await self._request_with_retry(
                client, "GET", url, provider_name="Spark Hub", headers=self._headers(),
            )
            data = resp.json()
            self._raise_business_error(data, "查询任务")
            status = _find(data, "status", "state", "task_status")
            status = str(status).lower() if status is not None else ""
            # 状态发生变化时回调（用于把上游 queued/running 等进度推给前端，避免进度条长时间不动）
            if status and status != last_status:
                last_status = status
                if self.on_status is not None:
                    try:
                        self.on_status(status, elapsed)
                    except Exception:
                        logger.warning("Spark Hub 进度回调失败（不影响任务轮询）", exc_info=True)
            if status in self._SUCCESS_STATUSES:
                return data
            if status in self._TERMINAL_FAILED:
                # 记录完整终态响应，便于事后排查（失败原因常藏在嵌套字段）
                logger.warning(
                    "Spark Hub 任务终态失败: task_id=%s status=%s body=%s",
                    task_id, status, json.dumps(data, ensure_ascii=False)[:2000],
                )
                err = await self._failure_detail(client, data, task_id)
                raise ProviderError(
                    f"Spark Hub 任务 {task_id} 未成功（status={status}）"
                    f"{('：' + err) if err else ''}",
                    submit_id=task_id,
                )
            if not status:
                # 状态字段缺失可能意味着结构差异，保守推进轮询
                await asyncio.sleep(self._POLL_INTERVAL)
                elapsed += self._POLL_INTERVAL
                continue
            await asyncio.sleep(self._POLL_INTERVAL)
            elapsed += self._POLL_INTERVAL
        raise ProviderError(
            f"Spark Hub 任务 {task_id} 轮询超时（>{int(self._POLL_TIMEOUT)}s）。"
            "重试将从已有 submit_id 断点续查，不会重复扣费",
            submit_id=task_id,
        )

    async def _failure_detail(self, client: httpx.AsyncClient, polled: dict[str, Any], task_id: str) -> str:
        """聚合终态失败的完整原因（可为空串）。

        优先级：query_task 响应里的失败描述 → 上游原始响应（original_response）
        中的底层模型错误（error.code + error.message）→ 空串。
        命中已知内容安全错误码时附加修复建议。
        """
        reason = ""
        # 1) 查询响应里的失败描述：跳过空串占位（顶层常为 "error": ""），
        #    避免 _find 按顺序取到空值而吞掉嵌套的真实 message。
        for key in _FAILURE_KEYS:
            val = _find_nonempty(polled, key)
            if val:
                reason = str(val).strip()
                break
        # 2) 兜底：查询上游原始响应，取底层模型的结构化错误（更精确）。
        if not reason:
            try:
                url = f"{self.base_url}{_ORIGINAL_PATH.format(task_id=task_id)}"
                resp = await self._request_with_retry(
                    client, "GET", url, provider_name="Spark Hub 原始响应", headers=self._headers(),
                )
                parts = _collect_error_parts(resp.json())
                if parts:
                    reason = "；".join(parts)
            except Exception:
                logger.debug("Spark Hub 获取原始失败响应失败（不影响终态判定）", exc_info=True)
        if reason:
            hint = _content_hint(reason)
            if hint:
                reason = f"{reason}。{hint}"
        return reason

    async def _download(self, url: str) -> bytes:
        """下载结果字节（CDN 链接，瞬时故障自动重试）。"""
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await self._request_with_retry(
                client, "GET", url, provider_name="Spark Hub 结果下载",
            )
        return resp.content

    # ---------- 模板方法：提交 → 轮询 → 提取 URL → 下载 ----------

    async def _run_task(
        self,
        payload: dict[str, Any],
        pick_urls: Callable[[dict[str, Any]], list[str]],
        mime_type: str,
    ) -> GenerationResult:
        """提交任务并等待结果，构造 GenerationResult。"""
        async with httpx.AsyncClient(timeout=120) as client:
            task_id = await self._submit(client, payload)
            polled = await self._poll(client, task_id)

        urls = pick_urls(polled)
        if not urls:
            raise ProviderError(f"Spark Hub 任务 {task_id} 成功但未返回结果 URL：{polled}")
        file_bytes = await self._download(urls[0])
        return GenerationResult(
            file_bytes=file_bytes,
            mime_type=mime_type,
            metadata={"model": payload.get("api_name", ""), "task_id": task_id, "urls": urls},
        )

    # ---------- 抽象方法由子类实现 ----------

    def _build_create_payload(self, prompt: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _extract_result_urls(self, polled: dict[str, Any]) -> list[str]:
        raise NotImplementedError

    def _result_mime(self) -> str:
        raise NotImplementedError

    async def test_connection(self) -> bool:
        """探测连通性：真实发起一次最小文本任务，通过创建结果判断 key 是否有效。

        使用文本模型 doubao_seed_2_1_turbo（成本极低）POST /task/create_task。
        鉴权在创建任务时校验：Key 无效 / 账号停用 / 未开通等会抛出带修复建议的
        ProviderError；能成功拿到 task_id 即说明 API Key 有效、服务可达。
        仅创建任务、不轮询到出图，避免无谓消耗。
        """
        if not self.api_key:
            raise ProviderError("Spark Hub API Key 未配置，请在设置页填写")
        payload = {
            "api_name": "doubao_seed_2_1_turbo",
            "prompt": "ping",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            await self._submit(client, payload)
        return True
