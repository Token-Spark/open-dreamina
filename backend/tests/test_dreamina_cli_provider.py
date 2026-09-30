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

"""即梦画布 CLI Provider / 服务层测试：以假 CLI 输出覆盖新版 dreamina-canvas 契约。

不执行真实子进程：monkeypatch DreaminaCliBaseProvider._run_cli 与
dreamina_cli_service._run，按命令签名路由到预设的 envelope 响应。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.providers.base import ProviderError
from app.providers.dreamina_cli_provider import (
    DreaminaSeedanceProvider,
    DreaminaSeedreamProvider,
    _image_resolution_type,
    _ratio_from_size,
    _slugify_title,
    _video_ratio_from_size,
)


def envelope(ok: bool, data: dict | None = None, error: dict | None = None, partial: dict | None = None) -> str:
    body: dict = {"schemaVersion": "1", "ok": ok}
    if ok:
        body["data"] = data or {}
    else:
        body["error"] = {"code": "service.1", "class": "service_failure", "message": "boom", **(error or {})}
    if partial is not None:
        body["partialData"] = partial
    return json.dumps(body, ensure_ascii=False)


class FakeCli:
    """按命令前缀路由的 CLI 替身：routes 为 [(前缀元组, (exit_code, output))]。"""

    def __init__(self, routes: list[tuple[tuple[str, ...], tuple[int, str]]]):
        self.routes = routes
        self.calls: list[list[str]] = []

    async def __call__(self, args: list[str], timeout: float | None = None) -> tuple[int, str]:
        self.calls.append(list(args))
        for prefix, response in self.routes:
            if tuple(args[: len(prefix)]) == prefix:
                return response
        raise AssertionError(f"FakeCli 未配置命令路由: {args}")


def make_video_provider(**config) -> DreaminaSeedanceProvider:
    return DreaminaSeedanceProvider(config={"model_id": "seedance2.5", **config})


def make_image_provider(**config) -> DreaminaSeedreamProvider:
    return DreaminaSeedreamProvider(config={"model_id": "seedream5.0", **config})


# ============================== 基础工具函数 ==============================


def test_video_ratio_from_size_nearest_match():
    # 480×864 约简为 10:18，不是合法枚举；应取最接近的 9:16
    assert _video_ratio_from_size(480, 864) == "9:16"
    assert _video_ratio_from_size(1920, 1080) == "16:9"
    assert _video_ratio_from_size(0, 0) == "16:9"


def test_ratio_from_size_gcd_and_fallback():
    assert _ratio_from_size(1024, 1024) == "1:1"
    assert _ratio_from_size(1920, 1080) == "16:9"
    # 大数约简超过 64 时取最接近的常见比例
    assert _ratio_from_size(4096, 2160) in {"21:9", "16:9"}


def test_image_resolution_tiers():
    assert _image_resolution_type("seedream5.0", 2048, 2048, "4K") == "4k"
    # 请求档位不被模型支持时回退 2k
    assert _image_resolution_type("jimeng3.1", 2048, 2048, "4k") == "2k"
    # 无档位按最长边近似
    assert _image_resolution_type("jimeng3.1", 1024, 1024) == "1k"
    assert _image_resolution_type("seedream5.0", 2048, 1024) == "2k"


def test_slugify_title():
    assert _slugify_title("一只橘猫坐在窗台上，清晨柔光", "fb") == "一只橘猫坐在窗台上，清晨柔光"[:24]
    assert _slugify_title("", "fallback") == "fallback"
    assert _slugify_title("   ", "fallback") == "fallback"


# ============================== envelope 解析与错误分类 ==============================


def test_parse_envelope_merges_partial_data():
    provider = make_video_provider()
    ok, data, error = provider._parse_envelope(
        envelope(False, error={"code": "cli.generation_confirmation_required"},
                 partial={"items": [{"nodeId": "node_a", "submitId": "s-1"}]}),
        "提交",
    )
    assert ok is False
    assert error["code"] == "cli.generation_confirmation_required"
    assert data["partialData"]["items"][0]["submitId"] == "s-1"


def test_parse_envelope_invalid_json_raises_upgrade_hint():
    provider = make_video_provider()
    with pytest.raises(ProviderError) as exc:
        provider._parse_envelope("fatal error: not json", "user_credit")
    assert "升级" in str(exc.value)


def test_classify_auth_and_confirm_errors():
    provider = make_video_provider()
    auth_fix = provider._classify_error(
        envelope(False, error={"class": "auth_required", "requiredAction": "login"})
    )
    assert auth_fix and "重新完成登录" in auth_fix
    confirm_fix = provider._classify_error('{"error":{"code":"cli.generation_confirmation_required"}}')
    assert confirm_fix and "credit_ceiling" in confirm_fix


# ============================== 画布解析 ==============================


def test_canvas_explicit_id_skips_lookup():
    provider = make_video_provider(canvas_id="proj-explicit")
    fake = FakeCli([])
    provider._run_cli = fake  # type: ignore[method-assign]
    project_id, web_url = asyncio.run(provider._ensure_canvas())
    assert project_id == "proj-explicit"
    assert web_url is None
    assert fake.calls == []  # 显式画布不触发任何 CLI 调用


def test_canvas_reused_from_ls():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("canvas", "ls"), (0, envelope(True, {"items": [
            {"projectId": "proj-1", "name": "其他画布", "webUrl": "https://w/1"},
            {"projectId": "proj-2", "name": "Open Dreamina", "webUrl": "https://w/2"},
        ]}))),
    ])
    project_id, web_url = asyncio.run(provider._ensure_canvas())
    assert (project_id, web_url) == ("proj-2", "https://w/2")


def test_canvas_created_when_missing():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("canvas", "ls"), (0, envelope(True, {"items": []}))),
        (("canvas", "create"), (0, envelope(True, {
            "project": {"projectId": "proj-new", "name": "Open Dreamina", "webUrl": "https://w/new"}
        }))),
    ])
    project_id, _ = asyncio.run(provider._ensure_canvas())
    assert project_id == "proj-new"


# ============================== 模型解析 ==============================


def test_model_map_override():
    provider = make_video_provider(model_map={"seedance2.5": "seedance_2_5_custom"})
    assert asyncio.run(provider._resolve_model("seedance2.5", "video")) == "seedance_2_5_custom"


def test_model_find_matches_alias_variant():
    provider = make_video_provider()
    fake = FakeCli([
        (("model", "find"), (0, envelope(True, {"query": "seedance 2.5", "matches": [
            {"model": "seedance_2.5_fast", "aliases": ["Seedance 2.5"]},
        ]}))),
    ])
    provider._run_cli = fake  # type: ignore[method-assign]
    canonical = asyncio.run(provider._resolve_model("seedance2.5", "video"))
    assert canonical == "seedance_2.5_fast"
    # 候选关键词按序尝试：首个即原样 model_id
    assert fake.calls[0][2] == "seedance2.5"


def test_model_find_fallback_to_raw_when_all_miss():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("model", "find"), (0, envelope(False, error={"code": "cli.not_found"}))),
    ])
    assert asyncio.run(provider._resolve_model("unknown-model", "video")) == "unknown-model"


# ============================== Seedance 参数组装 ==============================


def _upload_routes(resource_ids: list[str]) -> list[tuple[tuple[str, ...], tuple[int, str]]]:
    routes = []
    for i, rid in enumerate(resource_ids):
        routes.append((
            ("resource", "upload", "--project-id", "proj-1", "--file", f"/tmp/in_{i}.png"),
            (0, envelope(True, {"resourceId": rid, "mediaType": "image/png"})),
        ))
    return routes


def test_t2v_args_no_reference():
    provider = make_video_provider(canvas_id="proj-1")
    fake = FakeCli([
        (("model", "find"), (0, envelope(True, {"matches": [{"model": "seedance_2.5"}]}))),
    ])
    provider._run_cli = fake  # type: ignore[method-assign]
    args = asyncio.run(provider._build_submit_args(
        {"prompt": "城市夜景", "duration": 5, "width": 1920, "height": 1080}, "proj-1", []
    ))
    text = " ".join(args)
    assert "--mode t2v" in text
    assert "--model seedance_2.5" in text
    assert "--ratio 16:9" in text
    assert "--resolution 720p" in text
    assert "--duration 5" in text
    assert "--run --credit-ceiling 200" in text
    assert "--ref" not in text


def test_first_last_frame_args_uploads_refs():
    provider = make_video_provider(canvas_id="proj-1")
    fake = FakeCli([
        (("model", "find"), (0, envelope(True, {"matches": [{"model": "seedance_2.5"}]}))),
        *_upload_routes(["res-uuid-1", "res-uuid-2"]),
    ])
    provider._run_cli = fake  # type: ignore[method-assign]
    args = asyncio.run(provider._build_submit_args(
        {"prompt": "过渡", "frame_mode": "first_last"}, "proj-1", ["/tmp/in_0.png", "/tmp/in_1.png"]
    ))
    text = " ".join(args)
    assert "--mode first_last_frame" in text
    assert text.count("--ref res:") == 2
    assert "res-uuid-1" in text and "res-uuid-2" in text
    # 有参考图时比例由素材决定，不传 --ratio
    assert "--ratio" not in text


def test_multimodal_reference_args():
    provider = make_video_provider(canvas_id="proj-1")
    fake = FakeCli([
        (("model", "find"), (0, envelope(True, {"matches": [{"model": "seedance_2.5"}]}))),
        *_upload_routes(["r1", "r2", "r3"]),
    ])
    provider._run_cli = fake  # type: ignore[method-assign]
    args = asyncio.run(provider._build_submit_args(
        {"prompt": "多参考", "frame_mode": "reference"}, "proj-1", [f"/tmp/in_{i}.png" for i in range(3)]
    ))
    text = " ".join(args)
    assert "--mode m2v" in text
    assert text.count("--ref res:") == 3


# ============================== Seedream 参数组装 ==============================


def test_t2i_args_with_size_and_count():
    provider = make_image_provider(canvas_id="proj-1")
    fake = FakeCli([
        (("model", "find"), (0, envelope(True, {"matches": [{"model": "seedream_5.0"}]}))),
    ])
    provider._run_cli = fake  # type: ignore[method-assign]
    args = asyncio.run(provider._build_submit_args(
        {"prompt": "海报", "width": 2048, "height": 2048, "resolution": "4K", "count": 2},
        "proj-1", [],
    ))
    text = " ".join(args)
    assert "--mode t2i" in text
    assert "--model seedream_5.0" in text
    assert "--ratio 1:1" in text
    assert "--resolution 4k" in text
    assert "--count 2" in text
    assert "--run --credit-ceiling 200" in text


def test_i2i_args_uploads_refs():
    provider = make_image_provider(canvas_id="proj-1")
    fake = FakeCli([
        (("model", "find"), (0, envelope(True, {"matches": [{"model": "seedream_5.0"}]}))),
        *_upload_routes(["img-1"]),
    ])
    provider._run_cli = fake  # type: ignore[method-assign]
    args = asyncio.run(provider._build_submit_args(
        {"prompt": "改风格"}, "proj-1", ["/tmp/in_0.png"]
    ))
    text = " ".join(args)
    assert "--mode i2i" in text
    assert "--ref res:img-1" in text


# ============================== 提交 / 轮询 / 下载 ==============================


def test_submit_extracts_submit_id_from_items():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("node", "create"), (0, envelope(True, {"items": [
            {"nodeId": "node_v1", "submitId": "sub-1", "state": "ACCEPTED"}
        ]}))),
    ])
    submit_id, node_id, _data = asyncio.run(provider._submit(["node", "create", "video"]))
    assert submit_id == "sub-1"
    assert node_id == "node_v1"


def test_submit_extracts_submit_id_from_node_resources():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("node", "create"), (0, envelope(True, {"node": {
            "nodeId": "node_v2",
            "resources": [{"resourceId": "r-1", "submitId": "sub-2", "creditsAmount": 12}],
        }}))),
    ])
    submit_id, node_id, data = asyncio.run(provider._submit(["node", "create", "video"]))
    assert submit_id == "sub-2"
    assert node_id == "node_v2"
    assert provider._extract_credits(data) == 12


def test_submit_confirmation_required_carries_submit_id():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("node", "create"), (10, envelope(
            False,
            error={"code": "cli.generation_confirmation_required", "requiredAction": "confirm"},
            partial={"items": [{"nodeId": "n", "submitId": "s-pending"}]},
        ))),
    ])
    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider._submit(["node", "create", "video"]))
    assert exc.value.submit_id == "s-pending"
    assert "积分上限" in str(exc.value)


def test_wait_operation_success_downloads_resources(tmp_path: Path):
    provider = make_video_provider()
    # operation wait 成功 + 资源就绪
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("operation", "wait"), (0, envelope(True, {
            "operationRef": "sub-1", "state": "succeeded",
            "resources": [{"resourceId": "res-final", "state": "succeeded",
                           "width": 1920, "height": 1080, "format": "mp4"}],
        }))),
        (("resource", "download"), (0, _write_download(tmp_path, "res-final", "video.mp4", b"MP4DATA"))),
    ])
    resources = asyncio.run(provider._wait_operation("proj-1", "sub-1"))
    assert resources[0]["resourceId"] == "res-final"
    files, _ = asyncio.run(provider._download_resources("proj-1", resources, str(tmp_path)))
    assert files[0][0] == b"MP4DATA"
    assert files[0][1] == "video/mp4"


def _write_download(tmp_path: Path, resource_id: str, name: str, content: bytes) -> str:
    """模拟 resource download：CLI 把文件写到 --output 目录，返回 envelope 文本。"""
    target = tmp_path / name
    target.write_bytes(content)
    return envelope(True, {"resourceId": resource_id, "path": str(target),
                           "size": len(content), "sha256": "abc"})


def test_wait_operation_retries_on_exit_20(tmp_path: Path):
    provider = make_video_provider()
    provider._POLL_INTERVAL = 0  # 测试中不真实睡眠
    calls = {"n": 0}

    async def fake_run(args, timeout=None):
        if args[:2] == ["operation", "wait"]:
            calls["n"] += 1
            if calls["n"] == 1:
                return 20, envelope(False, error={
                    "class": "operation_incomplete", "requiredAction": "resume",
                })
            return 0, envelope(True, {
                "state": "succeeded",
                "resources": [{"resourceId": "r", "state": "succeeded"}],
            })
        raise AssertionError(args)

    provider._run_cli = fake_run  # type: ignore[method-assign]
    resources = asyncio.run(provider._wait_operation("proj-1", "sub-1"))
    assert calls["n"] == 2
    assert resources[0]["resourceId"] == "r"


def test_wait_operation_fail_state_raises():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("operation", "wait"), (0, envelope(True, {
            "state": "failed",
            "submissionError": {"message": "content policy violation"},
        }))),
    ])
    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider._wait_operation("proj-1", "sub-1"))
    assert "content policy violation" in str(exc.value)
    assert exc.value.submit_id == "sub-1"


def test_generate_end_to_end(tmp_path: Path, monkeypatch):
    import time as _time

    provider = make_video_provider(canvas_id="proj-1")
    provider._cli_checked_at = _time.monotonic()  # 处于 TTL 缓存内，跳过 auth status 探测

    async def fake_run(args, timeout=None):
        if args[:2] == ["model", "find"]:
            return 0, envelope(True, {"matches": [{"model": "seedance_2.5"}]})
        if args[:2] == ["resource", "upload"]:
            return 0, envelope(True, {"resourceId": "res-uploaded", "mediaType": "image/png"})
        if args[:2] == ["node", "create"]:
            return 0, envelope(True, {"items": [
                {"nodeId": "node-e2e", "submitId": "sub-e2e", "state": "ACCEPTED"}
            ]})
        if args[:2] == ["operation", "wait"]:
            target = tmp_path / "out.mp4"
            target.write_bytes(b"RESULT")
            return 0, envelope(True, {
                "state": "succeeded",
                "resources": [{"resourceId": "res-out", "state": "succeeded",
                               "width": 1280, "height": 720, "format": "mp4"}],
            })
        if args[:2] == ["resource", "download"]:
            target = tmp_path / "downloaded.mp4"
            target.write_bytes(b"RESULT")
            return 0, envelope(True, {"resourceId": "res-out", "path": str(target), "size": 6})
        raise AssertionError(args)

    provider._run_cli = fake_run  # type: ignore[method-assign]
    result = asyncio.run(provider.image_to_video(
        b"PNGDATA", prompt="一只橘猫", duration=5, width=1280, height=720,
    ))
    assert result.file_bytes == b"RESULT"
    assert result.metadata["task_id"] == "sub-e2e"
    assert result.metadata["node_id"] == "node-e2e"
    assert result.metadata["project_id"] == "proj-1"
    assert result.metadata["model"] == "seedance2.5"
    assert result.metadata["width"] == 1280
    assert result.mime_type == "video/mp4"


# ============================== 连通性检查 ==============================


def test_ensure_cli_available_rejects_logged_out():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("auth", "status"), (0, envelope(True, {"loggedIn": False}))),
    ])
    with pytest.raises(ProviderError) as exc:
        asyncio.run(provider._ensure_cli_available())
    assert "登录" in str(exc.value)


def test_ensure_cli_available_caches():
    provider = make_video_provider()
    calls = {"n": 0}

    async def fake_run(args, timeout=None):
        calls["n"] += 1
        return 0, envelope(True, {"loggedIn": True})

    provider._run_cli = fake_run  # type: ignore[method-assign]
    asyncio.run(provider._ensure_cli_available())
    asyncio.run(provider._ensure_cli_available())
    assert calls["n"] == 1  # TTL 缓存内不重复探测


def test_test_connection_success():
    provider = make_video_provider()
    provider._run_cli = FakeCli([  # type: ignore[method-assign]
        (("auth", "account"), (0, envelope(True, {"userId": 42, "isVip": True}))),
    ])
    assert asyncio.run(provider.test_connection()) is True


def test_missing_cli_error_mentions_legacy(monkeypatch):
    provider = make_video_provider()
    # 让 PATH 与 fallback 都找不到 dreamina-canvas，但存在旧版 dreamina
    monkeypatch.setattr("shutil.which", lambda name: None)
    legacy = Path("/tmp/od-test-legacy-dreamina")
    legacy.touch()
    monkeypatch.setattr(
        "app.providers.dreamina_cli_provider._LEGACY_CLI_FALLBACK_PATHS", (str(legacy),)
    )
    monkeypatch.setattr(
        "app.providers.dreamina_cli_provider._CLI_FALLBACK_PATHS", ()
    )
    error = provider._missing_cli_error()
    assert "dreamina-canvas" in str(error)
    assert "旧版" in str(error)
    legacy.unlink()


# ============================== 服务层（安装/登录） ==============================


class FakeRedis:
    """同步 dict 替身：覆盖 service 用到的 get/set/delete/incr/expire。"""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)

    def incr(self, key):
        self.store[key] = str(int(self.store.get(key, "0") or 0) + 1)
        return int(self.store[key])

    def expire(self, key, ttl):
        pass


@pytest.fixture()
def fake_service_env(monkeypatch):
    """替换 service 的 Redis / 子进程执行 / CLI 路径解析，返回 (svc, fake_redis, state)。"""
    from app.services import dreamina_cli_service as svc

    fake = FakeRedis()
    state: dict = {"routes": [], "calls": []}

    def fake_run(args, timeout=60.0):
        state["calls"].append(list(args))
        for prefix, response in state["routes"]:
            if tuple(args[: len(prefix)]) == prefix:
                return response
        raise AssertionError(f"fake_run 未配置命令路由: {args}")

    monkeypatch.setattr(svc, "_redis", lambda: fake)
    monkeypatch.setattr(svc, "_run", fake_run)
    monkeypatch.setattr(svc, "resolve_cli_path", lambda cli_path=None: "/fake/cli")
    return svc, fake, state


# 新版 auth login --non-interactive 的真实输出结构（2026-09-30 实测 v1.0.2）
_AUTH_LOGIN_OUTPUT = json.dumps({
    "schemaVersion": "1", "ok": True,
    "data": {
        "status": "authorization_required",
        "challenge": {
            "deviceCode": "dc-123",
            "userCode": "uc-456",
            "verificationUri": "https://jimeng.jianying.com/ai-tool/cli-auth",
            "verificationUriComplete": "https://jimeng.jianying.com/ai-tool/cli-auth?user_code=uc-456",
            "pollSeconds": 1,
            "expiresAt": "2026-10-01T00:01:40+08:00",
        },
        "profile": "default", "region": "cn",
    },
}, ensure_ascii=False)


def test_service_parse_version():
    from app.services import dreamina_cli_service as svc

    assert svc._parse_version(envelope(True, {"version": "1.0.2"})) == "1.0.2"
    assert svc._parse_version("dreamina-canvas 1.0.0 (ae2c968)") == "dreamina-canvas 1.0.0 (ae2c968)"
    assert svc._parse_version("") is None


def test_service_start_login_parses_challenge(fake_service_env):
    svc, fake, state = fake_service_env
    state["routes"] = [(("/fake/cli", "auth", "login"), (0, _AUTH_LOGIN_OUTPUT))]
    result = svc.start_login("/fake/cli")
    assert result["ok"] is True
    assert result["device_code"] == "dc-123"
    assert result["user_code"] == "uc-456"
    # verification_uri 优先取 verificationUriComplete（可直接打开授权）
    assert result["verification_uri"].endswith("user_code=uc-456")
    # 会话落 Redis 供 check_login 使用
    assert fake.get(svc._LOGIN_SESSION_KEY)


def test_service_check_login_success_and_waiting(fake_service_env):
    svc, fake, state = fake_service_env
    fake.set(svc._LOGIN_SESSION_KEY, json.dumps({"device_code": "dc", "cli_path": "/fake/cli"}))

    # 未完成授权：auth account 返回 auth_required
    state["routes"] = [(("/fake/cli", "auth", "account"), (11, envelope(
        False, error={"code": "cli.authentication_required", "class": "auth_required",
                      "requiredAction": "login"})))]
    waiting = svc.check_login()
    assert waiting["state"] == "waiting"
    assert waiting["logged_in"] is False

    # 完成授权：auth account 返回账号信息
    state["routes"] = [(("/fake/cli", "auth", "account"),
                        (0, envelope(True, {"userId": 42, "isVip": True})))]
    success = svc.check_login()
    assert success["state"] == "success"
    assert success["logged_in"] is True
    assert success["account_info"]["userId"] == 42


def test_service_check_login_no_session(fake_service_env):
    svc, _fake, _state = fake_service_env
    result = svc.check_login()
    assert result["state"] == "no_session"


def test_service_check_ready_legacy_hint(fake_service_env, monkeypatch, tmp_path):
    svc, _fake, state = fake_service_env
    legacy = tmp_path / "dreamina"
    legacy.touch()
    # CLI 完全找不到（覆盖 fixture 默认的已安装路径）
    monkeypatch.setattr(svc, "resolve_cli_path", lambda cli_path=None: None)
    monkeypatch.setattr(svc, "_FALLBACK_PATHS", ())
    monkeypatch.setattr(svc, "_LEGACY_FALLBACK_PATHS", (str(legacy),))
    monkeypatch.setattr("shutil.which", lambda name: None)
    # login shell 兜底探测也不可用
    state["routes"] = [(("bash", "-lc"), (1, ""))]
    result = svc.check_ready()
    assert result["success"] is False
    assert "旧版" in result["message"]


def test_service_get_status_logged_out(fake_service_env, monkeypatch):
    svc, fake, state = fake_service_env
    state["routes"] = [
        (("/fake/cli", "version"), (0, envelope(True, {"version": "1.0.2"}))),
        (("/fake/cli", "auth", "status"), (0, envelope(True, {"loggedIn": False}))),
    ]
    status = svc.get_status()
    assert status["installed"] is True
    assert status["version"] == "1.0.2"
    assert status["logged_in"] is False
    assert "未登录" in status["message"]


def test_service_get_status_logged_in(fake_service_env, monkeypatch):
    svc, fake, state = fake_service_env
    state["routes"] = [
        (("/fake/cli", "version"), (0, envelope(True, {"version": "1.0.2"}))),
        (("/fake/cli", "auth", "status"), (0, envelope(True, {"loggedIn": True}))),
        (("/fake/cli", "auth", "account"), (0, envelope(True, {"userId": 7, "isVip": False}))),
    ]
    status = svc.get_status()
    assert status["logged_in"] is True
    assert status["account_info"]["userId"] == 7
    assert status["message"] == "CLI 已就绪（登录态有效）"
