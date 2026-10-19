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

"""进程级共享 Redis 连接池。

为什么必须共享：SSE 进度端点每秒读一次 Redis，worker 每个进度台阶写一次。
此前每次调用都 `Redis.from_url(...)` 新建客户端，等于用「建 TCP 连接」代替「取连接」，
命令跑完后连接被销毁，在发起侧留下 TIME_WAIT 套接字，高频轮询下迅速堆积。

按 PID 键控：Celery prefork 子进程会继承父进程已建立的 socket，跨进程共用一条连接会导致
协议串流。以 PID 为键可保证 fork 之后每个进程各自建池、互不干扰。

调用方不得对返回实例调用 close()：那会关掉整个共享池。
"""
from __future__ import annotations

import os
import threading

import redis

from ..config import settings

# 连接 3s 快速失败：Redis 不可用时健康检查与轮询不应挂住调用方
_CONNECT_TIMEOUT = 3.0
# 单条命令读写 5s 上限：进度缓存都是毫秒级操作，超时说明 Redis 有问题，
# 让它失败（上层均已 try/except 降级）而不是无限阻塞 worker / 事件循环
_SOCKET_TIMEOUT = 5.0
_MAX_CONNECTIONS = 50
# 复用前探活：Redis 重启或网络抖动后，闲置连接先 ping 一次再交给业务，
# 避免首个请求拿到半死连接报 ConnectionError
_HEALTH_CHECK_INTERVAL = 30

_lock = threading.Lock()
_clients: dict[int, redis.Redis] = {}


def get_redis() -> redis.Redis:
    """返回本进程共享的 Redis 客户端。"""
    pid = os.getpid()
    client = _clients.get(pid)
    if client is not None:
        return client
    with _lock:
        client = _clients.get(pid)
        if client is None:
            client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=_CONNECT_TIMEOUT,
                socket_timeout=_SOCKET_TIMEOUT,
                max_connections=_MAX_CONNECTIONS,
                health_check_interval=_HEALTH_CHECK_INTERVAL,
            )
            _clients[pid] = client
        return client
