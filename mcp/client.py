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

"""后端 REST 客户端：仅使用 Python 标准库（urllib），零第三方依赖。

后端 FastAPI 统一前缀 `/api/v1`，默认端口 10130。
可用环境变量覆盖：
- `OPEN_DREAMINA_API_BASE`：例如 http://localhost:10130/api/v1
- `OPEN_DREAMINA_API_TIMEOUT`：单次请求超时秒数（默认 60）
"""
from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://localhost:10130/api/v1"
DEFAULT_TIMEOUT = 60.0
# 生成任务等待上限，防止智能体无限阻塞。
MAX_WAIT_TIMEOUT = 1800.0


class ApiError(RuntimeError):
    """后端返回非 2xx、网络不可达或响应无法解析。

    message 已包含「发生了什么 + 上下文 + 修复建议」，可直接回传给智能体。
    """

    def __init__(self, message: str, *, status: int | None = None, path: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.path = path

    def to_dict(self) -> dict[str, Any]:
        return {"error": str(self), "status": self.status, "path": self.path}


def _extract_error(raw: bytes, status: int) -> str:
    """从后端错误响应中提取可读信息（兼容 detail / error 两种结构）。"""
    text = raw.decode("utf-8", "replace").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text[:500] or f"HTTP {status} 无响应体"

    detail = data.get("detail", data.get("error", data))
    if isinstance(detail, dict):
        message = detail.get("message") or json.dumps(detail, ensure_ascii=False)
        fix = detail.get("fix")
        return f"{message}（修复建议：{fix}）" if fix else str(message)
    if isinstance(detail, list):
        return "; ".join(str(item.get("msg", item)) for item in detail)
    return str(detail)


class ApiClient:
    """后端 API 薄封装：JSON 请求 + multipart 上传。"""

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        env_base = os.environ.get("OPEN_DREAMINA_API_BASE", "").strip()
        self.base_url = (base_url or env_base or DEFAULT_BASE_URL).rstrip("/")
        env_timeout = os.environ.get("OPEN_DREAMINA_API_TIMEOUT", "").strip()
        self.timeout = float(timeout or env_timeout or DEFAULT_TIMEOUT)

    # ---------------- 内部 ----------------

    def _open(self, request: urllib.request.Request, timeout: float | None = None) -> Any:
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            raise ApiError(
                f"{_extract_error(raw, exc.code)}（接口 {request.get_method()} {request.full_url} 返回 HTTP {exc.code}）",
                status=exc.code,
                path=request.full_url,
            ) from exc
        except urllib.error.URLError as exc:
            raise ApiError(
                f"无法连接后端 {self.base_url}：{exc.reason}。"
                "请确认已执行 deploy.sh / deploy.ps1 启动服务且 10130 端口可访问，"
                "或用 OPEN_DREAMINA_API_BASE 指定正确地址。",
                path=request.full_url,
            ) from exc
        except TimeoutError as exc:
            raise ApiError(
                f"请求后端超时（{self.timeout}s）：{request.full_url}。"
                "生成类接口只返回 task_id 不会超时，若为查询接口请稍后重试。",
                path=request.full_url,
            ) from exc

        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(
                f"后端返回了非 JSON 响应：{raw[:200]!r}（{request.full_url}）",
                path=request.full_url,
            ) from exc

    # ---------------- 公开接口 ----------------

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        query: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """发起 JSON 请求；path 以 `/` 开头（不含 /api/v1 前缀）。"""
        url = f"{self.base_url}{path}"
        if query:
            filtered = {k: v for k, v in query.items() if v is not None}
            if filtered:
                url = f"{url}?{urllib.parse.urlencode(filtered)}"

        data: bytes | None = None
        headers = {"Accept": "application/json"}
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        return self._open(request, timeout=timeout)

    def upload_file(self, file_path: str, timeout: float | None = None) -> dict[str, Any]:
        """上传本地文件为参考素材（POST /assets/upload，multipart/form-data）。"""
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise ApiError(f"待上传文件不存在：{path}。请确认路径正确且为常规文件。")

        payload = path.read_bytes()
        if not payload:
            raise ApiError(f"待上传文件为空：{path}。请更换有效文件后重试。")

        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        boundary = f"----OpenDreaminaMCP{uuid.uuid4().hex}"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {mime}\r\n\r\n".encode("utf-8"),
                payload,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        request = urllib.request.Request(
            f"{self.base_url}/assets/upload", data=body, headers=headers, method="POST"
        )
        return self._open(request, timeout=timeout or max(self.timeout, 120.0))
