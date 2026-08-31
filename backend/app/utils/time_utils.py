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

"""统一时间戳生成工具。

产出带时区的 ISO 8601 字符串（如 ``2026-08-31T14:30:00+08:00``），
确保前端 ``new Date(str)`` 能正确解析为 UTC epoch，避免因浏览器/服务器时区
差异导致"已等待"时长计算错误。
"""

from datetime import datetime, timezone


def now_iso() -> str:
    """当前本地时间的 ISO 8601 字符串（带时区偏移）。

    使用 ``astimezone()`` 附加本地时区偏移，而非 UTC，使展示时间与
    服务器本地时间一致，同时 ``new Date()`` 可正确换算为 UTC epoch。
    """
    return datetime.now().astimezone().isoformat()
