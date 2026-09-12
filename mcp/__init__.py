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

"""Open Dreamina MCP 服务（纯标准库实现，零第三方依赖）。

- `server.py`：stdio JSON-RPC 入口
- `tools.py`：工具注册表（name / description / inputSchema）
- `handlers.py`：工具实现聚合入口
- `generate.py` / `tasks.py` / `conversations.py` / `discovery.py`：按领域划分的工具实现
- `payload.py` / `common.py`：共享的入参构造与出参整形
- `client.py`：后端 REST 客户端（urllib）
- `catalog.py` / `sizes.py`：模型目录与尺寸换算
"""

__all__ = [
    "server",
    "tools",
    "handlers",
    "generate",
    "tasks",
    "conversations",
    "discovery",
    "payload",
    "common",
    "client",
    "catalog",
    "sizes",
]
