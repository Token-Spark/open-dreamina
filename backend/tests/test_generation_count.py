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

"""单次生成数量（1-4）契约：Provider 解析钳制 + 创建任务入口校验。"""
from __future__ import annotations

import asyncio

import pytest


def test_resolve_generation_count_clamps_to_contract():
    from app.providers.base import resolve_generation_count

    assert resolve_generation_count({}) == 1
    assert resolve_generation_count({"count": None}) == 1
    assert resolve_generation_count({"count": "abc"}) == 1
    assert resolve_generation_count({"count": 0}) == 1
    assert resolve_generation_count({"count": -3}) == 1
    assert resolve_generation_count({"count": 2}) == 2
    assert resolve_generation_count({"count": "4"}) == 4
    # 外部调用方绕过 UI 提交超量时按上限执行，不放大上游请求
    assert resolve_generation_count({"count": 50}) == 4


def test_openai_provider_sends_capped_n(monkeypatch):
    """OpenAI 兼容 Provider 收到 count=50 时，上游请求体的 n 为 4。"""
    from app.providers.openai_provider import OpenAIProvider

    captured: dict[str, object] = {}

    class _Resp:
        def json(self) -> dict:
            return {"data": [{"b64_json": "aGVsbG8="}], "usage": {"total_tokens": 1}}

    async def _fake_post(payload):
        captured["payload"] = payload
        return _Resp()

    provider = OpenAIProvider("https://example.test/v1", "sk-test", {})
    monkeypatch.setattr(provider, "_post_generations", _fake_post)
    result = asyncio.run(provider.text_to_image(prompt="p", count=50))

    assert captured["payload"]["n"] == 4  # type: ignore[index]
    assert result.files == [(b"hello", "image/png")]


@pytest.fixture()
def no_enqueue(monkeypatch):
    """屏蔽 Celery 入队，测试只覆盖创建校验。"""

    class _TaskStub:
        @staticmethod
        def delay(_task_id: str) -> None:
            return None

    monkeypatch.setattr("app.routers.tasks.run_generation_task", _TaskStub)


def _create_task(client, params: dict) -> tuple[int, str]:
    resp = client.post(
        "/api/v1/tasks",
        json={"type": "text2img", "provider": "mock", "prompt": "一只橘猫", "params": params},
    )
    return resp.status_code, resp.text


def test_create_task_accepts_four_images(client, no_enqueue):
    code, text = _create_task(client, {"count": 4, "resolution": "2K"})
    assert code == 201, text


def test_create_task_rejects_over_limit(client, no_enqueue):
    code, text = _create_task(client, {"count": 5})
    assert code == 400, text
    assert "1-4" in text


def test_create_task_rejects_non_integer(client, no_enqueue):
    code, text = _create_task(client, {"count": "many"})
    assert code == 400, text


def test_create_task_without_count_is_allowed(client, no_enqueue):
    code, text = _create_task(client, {"aspect_ratio": "16:9"})
    assert code == 201, text
