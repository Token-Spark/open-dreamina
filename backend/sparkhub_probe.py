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

"""Spark Hub Seedance 生视频「实际进度与结果」可行性验证脚本。

目的：验证 Spark Hub 中转站 query_task 返回的真实响应结构——
  - 状态字段叫什么（status/state/task_status...）、有哪些状态值、各状态持续多久；
  - 是否存在真实的进度字段（progress/percent...），能否驱动前端进度条；
  - 终态成功后 result.videos 的真实结构（字符串 URL 数组？还是对象数组？）；
  - 一个最简单的 4 秒文生视频任务从提交到成功到底要多久，是否超出 _POLL_TIMEOUT(600s)。

用法（在仓库根目录执行，脚本会从 DB 读取已配置的 sparkhub-seedance API Key）：
    python3 backend/sparkhub_probe.py [--model doubao_seedance_2_fast] [--prompt "1 girl"] [--duration 4]

注意：会真实创建 Spark Hub 任务并产生计费，请确认 API Key 可用。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

import httpx  # noqa: E402

from app.database import db_session  # noqa: E402
from app.models import ApiProvider  # noqa: E402
from app.providers.sparkhub_base import _find  # noqa: E402
from app.providers.sparkhub_seedance import SparkHubSeedanceProvider  # noqa: E402
from app.utils.crypto import decrypt  # noqa: E402

_CREATE_PATH = "/task/create_task"
_QUERY_PATH = "/task/query_task/{task_id}"

# 目前实现里用于判定终态的取值（与 sparkhub_base._SUCCESS_STATUSES 对齐）
_CUR_SUCCESS = {"succeeded", "completed", "success"}
_CUR_FAILED = {"failed", "cancelled", "expired"}


def _mask_key(k: str) -> str:
    if not k:
        return "<empty>"
    if len(k) <= 8:
        return "****"
    return f"{k[:4]}****{k[-4:]}"


def _load_configured_provider() -> tuple[str, str, dict]:
    """从 DB 读取 sparkhub-seedance 的 base_url / api_key / config。"""
    with db_session() as db:
        row = db.query(ApiProvider).filter(ApiProvider.slug == "sparkhub-seedance").first()
        if not row:
            raise SystemExit("DB 中未配置 sparkhub-seedance Provider")
        api_key = decrypt(row.api_key_enc)
        base_url = row.base_url
        config = json.loads(row.config_json or "{}")
    return base_url, api_key, config


async def probe(args: argparse.Namespace) -> None:
    base_url, api_key, config = _load_configured_provider()
    print(f"[DB] base_url={base_url} api_key={_mask_key(api_key)} config={config}")

    provider = SparkHubSeedanceProvider(base_url=base_url, api_key=api_key, config=config)
    headers = provider._headers()

    payload = {
        "api_name": args.model,
        "prompt": args.prompt,
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "duration": args.duration,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        # ---------- 1. 提交任务 ----------
        t0 = time.perf_counter()
        resp = await client.post(f"{base_url}{_CREATE_PATH}", headers=headers, json=payload)
        submit_ms = (time.perf_counter() - t0) * 1000
        body = resp.json()
        print(f"\n=== 1. create_task HTTP {resp.status_code} ({submit_ms:.0f}ms) ===")
        print("response:", json.dumps(body, ensure_ascii=False, indent=2)[:2000])

        # 模拟 _submit 的解析：_find(data, "task_id", "id", "data")
        task_id = _find(body, "task_id", "id", "data")
        if not isinstance(task_id, str) or not task_id:
            print("\n[!!] _submit 解析不到 task_id，当前实现会抛 ProviderError")
            return
        print(f"[submit] 解析到 task_id = {task_id}")

        # ---------- 2. 细粒度轮询，观察真实响应结构与状态迁移 ----------
        print(f"\n=== 2. query_task 轮询（每 {args.interval}s，观察状态/进度字段）===")
        url = f"{base_url}{_QUERY_PATH.format(task_id=task_id)}"
        prev_status: str | None = None
        first_status_at: float | None = None
        terminal = None
        transitions: list[tuple[float, str, object]] = []
        progress_hist: list[tuple[float, object]] = []

        # 统计各轮询响应中出现过的 key 集合，识别真实字段名
        keys_seen: dict[str, int] = {}

        for i in range(args.max_polls):
            t = time.perf_counter()
            r = await client.get(url, headers=headers)
            data = r.json()
            elapsed = time.perf_counter() - t

            for k in data.keys():
                keys_seen[k] = keys_seen.get(k, 0) + 1

            status = str(_find(data, "status", "state", "task_status")).lower()
            # 记录所有候选进度字段的取值，观察是否上报真实进度
            for pk in ("progress", "percent", "progress_rate", "process"):
                if pk in data or any(isinstance(v, dict) and pk in v for v in data.values() if isinstance(v, dict)):
                    val = _find(data, pk)
                    if isinstance(val, (int, float)):
                        progress_hist.append((elapsed_total := i * args.interval, val))

            if first_status_at is None and status:
                first_status_at = time.perf_counter()

            if status != prev_status:
                prev_status = status
                transitions.append((round(time.perf_counter() - t0, 1), status, _compact(data)))
                print(f"[t={time.perf_counter()-t0:6.1f}s] status={status!r}  (单次请求 {elapsed*1000:.0f}ms)")
                if args.verbose:
                    print("   body:", json.dumps(data, ensure_ascii=False)[:800])

            # 用当前实现同样的判定逻辑，看能否识别终态
            if status in _CUR_SUCCESS or status in _CUR_FAILED:
                terminal = (status, data, round(time.perf_counter() - t0, 1))
                break

            if i % 10 == 0 and args.verbose:
                print(f"   [t={time.perf_counter()-t0:6.1f}s] 未到终态，继续轮询…")

            await asyncio.sleep(args.interval)
            if time.perf_counter() - t0 > args.max_wait:
                break

        # ---------- 3. 汇总 ----------
        print(f"\n=== 3. 汇总 ===")
        print(f"create_task 耗时: {submit_ms:.0f}ms")
        print(f"query_task 中出现的顶层字段: {sorted(keys_seen.keys())}")
        print(f"状态迁移时间线（自提交起）:")
        for t, s, compact in transitions:
            print(f"  t={t:6.1f}s  status={s!r:16} body_keys={sorted(compact.keys())}")
        print(f"候选进度字段历史: {progress_hist[:20]}")

        if terminal is None:
            print(f"\n[!!] {args.max_wait}s 内未到终态，前端表现就是「无限等待」")
            return

        status, final_body, total_s = terminal
        print(f"\n=== 4. 终态（status={status!r}，共 {total_s}s）===")
        print("final body:", json.dumps(final_body, ensure_ascii=False, indent=2)[:3000])

        # 用当前实现验证结果 URL 提取
        urls = provider._extract_result_urls(final_body)
        print(f"\n[verify] _extract_result_urls 提取到 {len(urls)} 个 URL")
        for u in urls[:3]:
            print(f"   - {u[:160]}")

        # 统计 HTTP 错误 / 异常响应
        if status not in _CUR_SUCCESS:
            err = _find(final_body, "error", "message", "fail_reason")
            print(f"[!!] 任务未成功：{err}")


async def run_provider_end_to_end(args: argparse.Namespace) -> None:
    """端到端验证：直接调用修复后的 provider.text_to_video，模拟真实生产路径。

    验证：_poll 能在 status=completed 时正常返回；结果 URL 提取、下载、落盘均成功。
    """
    base_url, api_key, config = _load_configured_provider()
    print(f"[DB] base_url={base_url} api_key={_mask_key(api_key)} config={config}")
    provider = SparkHubSeedanceProvider(base_url=base_url, api_key=api_key, config=config)

    transitions: list[str] = []
    provider.on_status = lambda s, e: transitions.append(f"{s}@{int(e)}s")

    t0 = time.perf_counter()
    result = await provider.text_to_video(
        prompt=args.prompt,
        duration=args.duration,
        model_id=args.model,
        width=1280,
        height=720,
    )
    total_s = time.perf_counter() - t0

    print(f"\n=== end-to-end text_to_video 结果 ===")
    print(f"上游状态迁移（status@elapsed）: {transitions}")
    print(f"总耗时（提交+轮询+下载）: {total_s:.1f}s")
    print(f"mime_type: {result.mime_type}")
    print(f"file_bytes: {len(result.file_bytes)} bytes")
    print(f"metadata: model={result.metadata.get('model')} task_id={result.metadata.get('task_id')} urls={len(result.metadata.get('urls', []))}")
    for u in result.metadata.get("urls", []):
        print(f"   url: {u[:160]}")
    head = result.file_bytes[:16]
    print(f"文件头魔数: {head[:4]!r}（mp4 应形如 b'\\x00\\x00\\x00...ftyp'）")
    if not result.file_bytes or not result.file_bytes.startswith(b"\x00\x00\x00"):
        print("[!!] 下载结果异常，不是有效 mp4")
    else:
        print("[OK] 端到端生成成功，视频有效")


def _compact(data: dict) -> dict:
    """压缩响应：只保留顶层标量字段名 + 值类型，便于时间线对比。"""
    out: dict = {}
    for k, v in data.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, list):
            out[k] = f"list[{len(v)}]"
        elif isinstance(v, dict):
            out[k] = f"dict{list(v.keys())[:5]}"
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Spark Hub Seedance 实际进度/结果探针")
    parser.add_argument("--model", default="doubao_seedance_2_fast", help="api_name")
    parser.add_argument("--prompt", default="1 girl", help="提示词")
    parser.add_argument("--duration", type=int, default=4, help="视频时长（秒）")
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--interval", type=float, default=2.0, help="轮询间隔（秒）")
    parser.add_argument("--max-polls", type=int, default=300)
    parser.add_argument("--max-wait", type=float, default=600.0, help="最长等待（秒）")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--end-to-end",
        action="store_true",
        help="端到端调用修复后的 provider.text_to_video（提交+轮询+下载）",
    )
    args = parser.parse_args()

    if args.end_to_end:
        asyncio.run(run_provider_end_to_end(args))
    else:
        asyncio.run(probe(args))


if __name__ == "__main__":
    main()
