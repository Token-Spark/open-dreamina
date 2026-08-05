"""性能测试脚本：测量 API 响应时间、并发任务、SSE 推送延迟。

运行方式: .venv\Scripts\python.exe perf_test.py
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request

BASE = "http://127.0.0.1:10130/api/v1"


def _get(path: str):
    start = time.perf_counter()
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        data = json.loads(resp.read())
    elapsed_ms = (time.perf_counter() - start) * 1000
    return data, elapsed_ms


def _post(path: str, body: dict):
    start = time.perf_counter()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    elapsed_ms = (time.perf_counter() - start) * 1000
    return data, elapsed_ms


def test_api_latency():
    """测试各 API 端点的响应延迟。"""
    print("=" * 60)
    print("1. API 响应延迟测试")
    print("=" * 60)
    endpoints = [
        ("GET", "/system/health", "健康检查"),
        ("GET", "/tasks?page_size=20", "任务列表"),
        ("GET", "/assets?page_size=24", "资产列表"),
        ("GET", "/providers", "Provider 列表"),
        ("GET", "/templates", "模板列表"),
    ]
    for method, path, label in endpoints:
        times = []
        for _ in range(10):
            _, ms = _get(path)
            times.append(ms)
        avg = sum(times) / len(times)
        p50 = sorted(times)[len(times) // 2]
        p99 = sorted(times)[-1]
        print(f"  {label:20s} avg={avg:7.1f}ms  p50={p50:7.1f}ms  p99={p99:7.1f}ms")


def test_concurrent_tasks(n: int = 5):
    """测试并发任务创建和完成时间。"""
    print()
    print("=" * 60)
    print(f"2. 并发任务测试 ({n} 个任务同时创建)")
    print("=" * 60)
    import concurrent.futures

    def create_and_wait(i: int):
        body = {
            "type": "text2img",
            "provider": "mock",
            "prompt": f"性能测试图 {i}",
            "params": {"width": 512, "height": 512, "steps": 10},
        }
        resp, create_ms = _post("/tasks", body)
        task_id = resp["task_id"]
        # 轮询等待完成
        start = time.perf_counter()
        while True:
            task, _ = _get(f"/tasks/{task_id}")
            if task["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.2)
            if time.perf_counter() - start > 30:
                return (i, create_ms, -1, "timeout")
        total_ms = (time.perf_counter() - start) * 1000
        return (i, create_ms, total_ms, task["status"])

    start_all = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(create_and_wait, range(n)))
    total_all = (time.perf_counter() - start_all) * 1000

    for i, create_ms, total_ms, status in results:
        print(f"  任务 {i}: 创建={create_ms:.0f}ms  完成等待={total_ms:.0f}ms  状态={status}")
    print(f"  总耗时: {total_all:.0f}ms (并行 {n} 个任务)")
    print(f"  平均每任务: {total_all / n:.0f}ms")


def test_sse_delivery():
    """测试 SSE 事件推送延迟。"""
    import httpx

    print()
    print("=" * 60)
    print("3. SSE 推送延迟测试")
    print("=" * 60)
    # 创建任务
    body = {
        "type": "text2img",
        "provider": "mock",
        "prompt": "SSE 延迟测试",
        "params": {"width": 256, "height": 256, "steps": 5},
    }
    resp, _ = _post("/tasks", body)
    task_id = resp["task_id"]

    # 订阅 SSE（用 httpx 流式读取）
    url = f"{BASE}/tasks/{task_id}/stream"
    start = time.perf_counter()
    first_event_time = None
    completed_time = None
    events = []

    with httpx.stream("GET", url, timeout=httpx.Timeout(connect=5, read=30, write=5, pool=5)) as resp:
        for line in resp.iter_lines():
            line = line.strip()
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
                events.append(event_type)
                if first_event_time is None:
                    first_event_time = time.perf_counter() - start
                if event_type == "completed":
                    completed_time = time.perf_counter() - start
                    break
            if time.perf_counter() - start > 15:
                break

    print(f"  任务 ID: {task_id}")
    print(f"  首个事件延迟: {first_event_time:.3f}s" if first_event_time else "  未收到事件")
    print(f"  完成事件延迟: {completed_time:.3f}s" if completed_time else "  未收到完成事件")
    print(f"  收到事件类型: {events}")


def test_db_query_performance():
    """测试数据库查询性能（任务列表 + 资产列表）。"""
    print()
    print("=" * 60)
    print("4. 数据库查询性能（批量请求）")
    print("=" * 60)
    for label, path in [("任务列表", "/tasks?page_size=50"), ("资产列表", "/assets?page_size=50")]:
        times = []
        for _ in range(20):
            _, ms = _get(path)
            times.append(ms)
        avg = sum(times) / len(times)
        print(f"  {label}: avg={avg:.1f}ms  min={min(times):.1f}ms  max={max(times):.1f}ms")


if __name__ == "__main__":
    test_api_latency()
    test_concurrent_tasks(5)
    test_sse_delivery()
    test_db_query_performance()
    print()
    print("=" * 60)
    print("性能测试完成")
    print("=" * 60)
