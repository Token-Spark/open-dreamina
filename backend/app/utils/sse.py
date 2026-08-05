"""SSE 响应辅助。"""
from __future__ import annotations

import json
from typing import Any


def format_event(event: str, data: Any) -> str:
    """格式化一个 SSE 事件块。

    数据若是 str 则原样写入，否则 JSON 序列化。
    """
    if isinstance(data, str):
        payload = data
    else:
        payload = json.dumps(data, ensure_ascii=False)

    # 每行 data: 前缀
    lines = payload.splitlines() or [""]
    body = "\n".join(f"data: {line}" for line in lines)
    return f"event: {event}\n{body}\n\n"


def heartbeat_event() -> str:
    return format_event("heartbeat", {})
