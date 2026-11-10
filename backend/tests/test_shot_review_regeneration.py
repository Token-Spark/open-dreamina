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

"""审阅中心任务卡片：剧目/类型标签解析与「改提示词 → 返工生成 → 采用为新版本」闭环。"""
from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.database import SessionLocal
from app.models import Asset, Task

SHOTS_MD = """# EP01 分镜

## EP01-S01

**镜头功能：** 开场建立人物与空间

**人物：** 林雪，米色风衣

**场景描述：** 圣诞夜的咖啡馆窗边，暖黄灯串

**秒级动作拆解：**
- 0-2s 推门进入，镜头缓慢后拉
- 2-5s 落座，抬眼看向窗外
"""


@pytest.fixture()
def drama_root(tmp_path, monkeypatch):
    """构造一部剧的目录结构，并把审片根目录指向它（含视频、分镜图与非镜号图片）。"""
    from PIL import Image

    root = tmp_path / "review_sources"
    episode = root / "圣诞男友" / "EP01"
    episode.mkdir(parents=True)
    (episode / "shots.md").write_text(SHOTS_MD, encoding="utf-8")
    (episode / "EP01-S01.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)

    buf = io.BytesIO()
    Image.new("RGB", (8, 12), color=(200, 120, 40)).save(buf, format="PNG")
    png = buf.getvalue()
    (episode / "EP01-S01_首帧.png").write_bytes(png)
    # 不以镜号命名的素材不应进入审片列表
    (episode / "角色定妆.png").write_bytes(png)

    monkeypatch.setattr(settings, "review_source_roots", str(root))
    monkeypatch.setattr(settings, "shot_review_source_roots", str(root))
    return root


@pytest.fixture()
def session_id(client, drama_root) -> str:
    resp = client.post(
        "/api/v1/shot-reviews/sessions",
        json={"title": "圣诞男友", "root_path": str(drama_root / "圣诞男友")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture()
def items(client, session_id) -> list[dict]:
    resp = client.get(f"/api/v1/shot-reviews/sessions/{session_id}/items")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _complete_task_with_asset(task_id: str, mime: str, suffix: str) -> str:
    """把返工任务置为 completed 并挂一个结果资产，返回 asset_id。"""
    rel_dir = Path("videos") / "2026-11"
    abs_dir = Path(settings.assets_dir) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"regen-{uuid.uuid4().hex[:8]}{suffix}"
    abs_file = abs_dir / file_name
    abs_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 128)

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task is not None
        asset = Asset(
            id=str(uuid.uuid4()),
            task_id=task.id,
            type="video" if mime.startswith("video/") else "image",
            file_path=str(rel_dir / file_name).replace("\\", "/"),
            file_size=abs_file.stat().st_size,
            mime_type=mime,
            width=704,
            height=1248,
            duration=5.0,
            tags_json="[]",
        )
        db.add(asset)
        params = json.loads(task.params_json)
        params["result_asset_ids"] = [asset.id]
        task.params_json = json.dumps(params)
        task.status = "completed"
        task.progress = 100
        db.commit()
        return asset.id


def test_scan_resolves_drama_episode_shot_and_content_type(items):
    """卡片标签的数据来源：剧目、剧集、镜头、内容类型、提示词底稿。"""
    assert len(items) == 2, items

    video = next(i for i in items if i["content_type"] == "video")
    image = next(i for i in items if i["content_type"] == "image")

    assert video["drama_title"] == "圣诞男友"
    assert video["episode"] == "EP01"
    assert video["shot_id"] == "EP01-S01"
    assert video["origin"] == "scan"
    assert video["asset_id"] is None
    # 提示词底稿取自同集 shots.md，供卡片上直接改写
    assert "林雪" in video["source_prompt"]

    assert image["content_type"] == "image"
    assert image["shot_id"] == "EP01-S01"
    assert image["drama_title"] == "圣诞男友"


def test_regenerate_then_adopt_creates_new_version(client, items, monkeypatch):
    """返工生成：提交 → 完成 → 采用为新版本（自动选定，旧版本取消选定）。"""
    from app.routers import shot_reviews as router_module

    monkeypatch.setattr(router_module.run_generation_task, "delay", lambda *a, **k: None)

    video = next(i for i in items if i["content_type"] == "video")
    # 先把原版本选定为保留版本，用于验证采用新版本后的互斥
    resp = client.patch(f"/api/v1/shot-reviews/items/{video['id']}", json={"selected": True})
    assert resp.status_code == 200, resp.text

    resp = client.post(
        f"/api/v1/shot-reviews/items/{video['id']}/regenerations",
        json={
            "prompt": "EP01-S01：林雪推门进入咖啡馆，暖黄灯串，镜头缓慢后拉",
            "provider": "mock",
            "model_id": "doubao-seedance-1-0-pro",
            "params": {"aspect_ratio": "9:16", "resolution": "720p", "duration": 5},
        },
    )
    assert resp.status_code == 201, resp.text
    regen = resp.json()
    assert regen["status"] == "pending"
    assert regen["shot_id"] == "EP01-S01"
    assert regen["task_type"] == "text2video"

    # 模拟 worker 完成生成
    asset_id = _complete_task_with_asset(regen["task_id"], "video/mp4", ".mp4")

    listed = client.get(f"/api/v1/shot-reviews/sessions/{regen['session_id']}/regenerations")
    assert listed.status_code == 200, listed.text
    synced = next(r for r in listed.json()["items"] if r["id"] == regen["id"])
    assert synced["status"] == "completed"
    assert synced["result_asset_id"] == asset_id
    assert synced["result_url"].endswith("/file")

    adopted = client.post(f"/api/v1/shot-reviews/regenerations/{regen['id']}/adopt")
    assert adopted.status_code == 200, adopted.text
    new_item = adopted.json()
    assert new_item["origin"] == "regen"
    assert new_item["asset_id"] == asset_id
    assert new_item["episode"] == "EP01"
    assert new_item["shot_id"] == "EP01-S01"
    assert new_item["selected"] is True
    assert new_item["drama_title"] == "圣诞男友"
    assert new_item["revised_prompt"].startswith("EP01-S01")

    # 同镜号现在有两个版本，新版本成为保留版本，原版本自动取消选定
    current = client.get(f"/api/v1/shot-reviews/sessions/{regen['session_id']}/items").json()
    same_shot = [i for i in current if i["shot_id"] == "EP01-S01" and i["content_type"] == "video"]
    assert len(same_shot) == 2
    original = next(i for i in same_shot if i["id"] == video["id"])
    assert original["selected"] is False

    # 返工产物走资产文件，审片接口可直接流式返回
    file_resp = client.get(f"/api/v1/shot-reviews/items/{new_item['id']}/file")
    assert file_resp.status_code == 200
    assert file_resp.content

    # 已采用的记录不可放弃
    discard = client.delete(f"/api/v1/shot-reviews/regenerations/{regen['id']}")
    assert discard.status_code == 400


def test_regeneration_requires_reference_for_img2img(client, items, monkeypatch):
    """图片条目返工默认 text2img；显式要求图生图但未给参考素材时如实报错。"""
    from app.routers import shot_reviews as router_module

    monkeypatch.setattr(router_module.run_generation_task, "delay", lambda *a, **k: None)

    image = next(i for i in items if i["content_type"] == "image")
    resp = client.post(
        f"/api/v1/shot-reviews/items/{image['id']}/regenerations",
        json={
            "prompt": "EP01-S01 首帧：林雪站在咖啡馆门口",
            "provider": "mock",
            "task_type": "img2img",
            "params": {"aspect_ratio": "9:16", "resolution": "2K"},
        },
    )
    assert resp.status_code == 400
    assert "参考素材" in resp.json()["detail"]["message"]

    ok = client.post(
        f"/api/v1/shot-reviews/items/{image['id']}/regenerations",
        json={
            "prompt": "EP01-S01 首帧：林雪站在咖啡馆门口",
            "provider": "mock",
            "params": {"aspect_ratio": "9:16", "resolution": "2K"},
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["task_type"] == "text2img"
