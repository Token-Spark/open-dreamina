#!/usr/bin/env python3
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

"""Open Dreamina MCP 服务入口（stdio 传输，纯 Python 标准库）。

用法：
    python mcp/server.py            # 启动 MCP 服务（供智能体 / IDE 以 stdio 连接）
    python -m mcp.server            # 等价写法（需在仓库根目录）
    python mcp/server.py --list-tools   # 打印工具清单（自检用，不启动服务）

stdout 只输出 JSON-RPC 报文，日志与异常栈一律走 stderr，避免污染协议流。
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

# 既支持 `python mcp/server.py`（脚本方式），也支持 `python -m mcp.server`（包方式）。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mcp import tools as tools_module
    from mcp.client import ApiClient, ApiError
else:
    from . import tools as tools_module
    from .client import ApiClient, ApiError

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "open-dreamina", "version": "1.0.0"}

INSTRUCTIONS = """Open Dreamina 生成能力网关（图片 / 视频 / 对话）。

推荐流程：
1. get_health 确认后端与 worker 就绪；list_providers / list_models 确认 provider、模型与可用参数。
2. generate_image 或 generate_video 创建任务（只返回 task_id，不会阻塞）。
3. wait_task 等待终态，再读取 result_urls_absolute 下载结果。

要点：
- provider 必填，取值为服务 slug（如 seedream / seedance-2-5 / openai）。
- 尺寸优先传 aspect_ratio + resolution，由服务换算像素；也可直接传 width + height。
- 传 reference_asset_ids 或 reference_paths 即自动切换为图生图 / 图生视频。
- 不传 conversation_id 时后端自动新建对话，可在返回值中读取。
- 失败任务用 retry_task 重试；长时间 pending 先用 get_health 检查 worker。
"""

_NOT_FOUND = -32601
_INVALID_REQUEST = -32600
_INVALID_PARAMS = -32602
_PARSE_ERROR = -32700
_INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    """协议层错误（区别于工具执行失败：后者以 isError=true 的 tool result 返回）。"""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _reply_result(msg_id: Any, result: Any) -> None:
    _write({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _reply_error(msg_id: Any, code: int, message: str, data: Any = None) -> None:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    _write({"jsonrpc": "2.0", "id": msg_id, "error": error})


def _tool_text(payload: Any, *, is_error: bool) -> dict[str, Any]:
    """MCP 工具结果统一用文本块承载 JSON，便于智能体直接解析。"""
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "isError": is_error,
    }


def _handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    """协商协议版本：优先回显客户端版本，避免因版本号不一致被判定为不兼容。"""
    requested = (params or {}).get("protocolVersion")
    return {
        "protocolVersion": requested or PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


def _handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    """执行工具：参数校验失败视为协议错误；后端调用失败视为工具错误。"""
    name = (params or {}).get("name") or ""
    arguments = (params or {}).get("arguments") or {}
    if not isinstance(arguments, dict):
        raise JsonRpcError(_INVALID_PARAMS, "arguments 必须是 JSON 对象。")

    try:
        tool = tools_module.validate_call(name, arguments)
    except KeyError as exc:
        raise JsonRpcError(_INVALID_PARAMS, str(exc)) from exc
    except ValueError as exc:
        raise JsonRpcError(_INVALID_PARAMS, str(exc)) from exc

    try:
        return _tool_text(tool["handler"](arguments, ApiClient()), is_error=False)
    except ApiError as exc:
        return _tool_text(exc.to_dict(), is_error=True)
    except Exception as exc:  # 兜底：任何实现缺陷都以工具错误回传，不让智能体侧连接中断
        traceback.print_exc(file=sys.stderr)
        return _tool_text(
            {"error": f"工具 {name} 执行异常：{type(exc).__name__}: {exc}", "hint": "请把该错误反馈给 MCP 服务维护者。"},
            is_error=True,
        )


def _dispatch(message: Any) -> None:
    if not isinstance(message, dict):
        _reply_error(None, _INVALID_REQUEST, "请求必须是 JSON-RPC 对象。")
        return

    msg_id = message.get("id")
    method = message.get("method")

    if not isinstance(method, str):
        if "id" in message:
            _reply_error(msg_id, _INVALID_REQUEST, "缺少字符串类型的 method 字段。")
        return

    if method.startswith("notifications/"):
        return  # 通知（notifications/initialized、notifications/cancelled 等）无需响应

    try:
        if method == "initialize":
            result = _handle_initialize(message.get("params") or {})
        elif method == "tools/list":
            result = {"tools": tools_module.TOOL_LISTINGS}
        elif method == "tools/call":
            result = _handle_tools_call(message.get("params") or {})
        elif method in ("ping", "shutdown"):
            result = {}
        else:
            raise JsonRpcError(_NOT_FOUND, f"不支持的方法 {method!r}；本服务仅提供 tools/list 与 tools/call。")
        _reply_result(msg_id, result)
    except JsonRpcError as exc:
        _reply_error(msg_id, exc.code, str(exc), exc.data)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        _reply_error(msg_id, _INTERNAL_ERROR, f"服务内部错误：{type(exc).__name__}: {exc}")


def main() -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if "--list-tools" in sys.argv:
        sys.stdout.write(json.dumps(tools_module.TOOL_LISTINGS, ensure_ascii=False, indent=2) + "\n")
        return 0

    print(f"[open-dreamina-mcp] 服务已启动，共 {len(tools_module.TOOLS)} 个工具。", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _reply_error(None, _PARSE_ERROR, f"JSON 解析失败：{exc}")
            continue
        _dispatch(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
