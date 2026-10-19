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

"""进程级共享 httpx AsyncClient（keep-alive 连接复用）。

为什么必须共享：每次调用各建一个 `httpx.AsyncClient` 意味着每个请求都要走一遍
TCP + TLS 握手，退出 `async with` 时主动 close 又在发起侧留下一个 TIME_WAIT 套接字。
Windows 默认动态端口只有 49152-65535（16384 个）、TIME_WAIT 保持 240 秒，且 Docker
Desktop 会把容器出网连接 NAT 到主机端口，因此高频生成/轮询会耗尽主机临时端口。
复用同一 client 后，同一上游主机全程共用一条 keep-alive 连接。

按事件循环键控：AsyncClient 与其连接绑定到创建它的事件循环，跨循环使用会报
"Event loop is closed"。Celery prefork 子进程与 uvicorn 主循环各自持有独立 client。
"""
from __future__ import annotations

import asyncio

import httpx

# 单次请求默认超时；各调用点仍可通过 timeout= 覆盖（生成 120s / 连通性测试 15s 等）。
# connect 收紧到 10s：上游不可达时快速失败，不让连接长期挂在 SYN 状态。
_DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0, pool=10.0)

# worker 并发 4 + API 轮询场景下 100 条上限足够；keep-alive 空闲连接保留 20 条，
# 既能跨任务复用，又不会让大量闲置连接长期 ESTABLISHED。
_MAX_CONNECTIONS = 100
_MAX_KEEPALIVE_CONNECTIONS = 20

_clients: dict[int, tuple[asyncio.AbstractEventLoop, httpx.AsyncClient]] = {}


def get_async_client() -> httpx.AsyncClient:
    """返回当前事件循环上的共享 client。调用方只可使用，不得 close()。"""
    loop = asyncio.get_running_loop()
    entry = _clients.get(id(loop))
    if entry is not None and entry[0] is loop and not entry[1].is_closed:
        return entry[1]
    # 键命中但对象不同 = 旧循环已被回收后 id 复用；持强引用可杜绝这种情况发生。
    # 走到这里只可能是旧循环已关闭，直接丢弃其 client（套接字随进程/循环释放）。
    client = httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        limits=httpx.Limits(
            max_connections=_MAX_CONNECTIONS,
            max_keepalive_connections=_MAX_KEEPALIVE_CONNECTIONS,
        ),
        # 不继承容器/宿主机代理环境变量：这些 client 长期存活，
        # 一旦被 HTTP(S)_PROXY 接管会把所有上游流量串到一个代理进程上。
        trust_env=False,
    )
    _clients[id(loop)] = (loop, client)
    return client


async def dispose_async_client() -> None:
    """关闭并移除当前事件循环上的共享 client（进程/循环退出前调用）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    entry = _clients.pop(id(loop), None)
    if entry is not None and entry[0] is loop and not entry[1].is_closed:
        await entry[1].aclose()
