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

"""镜头审片扫描门禁：只把能唯一定位到 EPxx-Sxx 的镜头放进审片列表。

覆盖三类不该出现的卡片：downloads 连拍母版、无镜号的开头样片整段、
只有镜号没有集号的分段样片；以及重新扫描时清理历史脏条目、保留已打分结果。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.config import settings

_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


@pytest.fixture()
def project(tmp_path, monkeypatch, png_bytes) -> Path:
    """混合布局：正式成片 + 关键帧 + 各种中间产物/样片。"""
    root = tmp_path / "review_sources"
    project = root / "圣诞男友"

    def put(rel: str, data: bytes = _MP4) -> None:
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    # 可逐镜审阅的交付物
    for rel in (
        "08_成片制作/EP01/video_renders/S01_seedance25/EP01-S01.mp4",
        "08_成片制作/EP01/video_renders/S02_seedance25/EP01-S02.mp4",
        "08_成片制作/EP02/video_renders/S01_seedance25/EP02-S01.mp4",
    ):
        put(rel)
    put("08_成片制作/EP01/video_renders/S01_seedance25/EP01-S01.png", png_bytes)
    # downloads 连拍母版：既有无镜号的，也有伪装成镜头名的
    put("08_成片制作/downloads/EP01/TG01_master.mp4")
    put("08_成片制作/downloads/EP01/EP01-S01_master.mp4")
    # 开头样片：整段视频、只有镜号没有集号的分段
    put("06_开头样片/EP01_开头样片_720p_对白版.mp4")
    put("06_开头样片/clips/S01.mp4")
    put("06_开头样片/clips_new/S02.mp4")
    # _ 前缀历史版本、无镜号场景参考图、跨镜共用的背景板（文件名含两个镜号）
    put("08_成片制作/EP01/video_renders/_takes/EP01-S01_take2.mp4")
    put("04_制作资产/assets/scenes/scene_shop.png", png_bytes)
    put("04_制作资产/assets/scenes/scene_estate/ep01_s08_s12_backdrop.png", png_bytes)

    monkeypatch.setattr(settings, "review_source_roots", str(root))
    monkeypatch.setattr(settings, "shot_review_source_roots", str(root))
    return project


def _create_session(client, project: Path, *, scan: bool = True) -> dict:
    resp = client.post(
        f"/api/v1/shot-reviews/sessions?scan={'true' if scan else 'false'}",
        json={"title": "扫描门禁测试", "root_path": str(project)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _items(client, session_id: str) -> list[dict]:
    resp = client.get(f"/api/v1/shot-reviews/sessions/{session_id}/items")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_scan_only_collects_identified_shots(client, project):
    """扫描只收 3 个成片 + 1 张关键帧，母版/样片/参考图一律不进列表。"""
    session = _create_session(client, project)
    items = _items(client, session["id"])

    assert session["item_count"] == 4
    assert sorted(i["shot_id"] for i in items) == [
        "EP01-S01", "EP01-S01", "EP01-S02", "EP02-S01",
    ]
    assert all(i["episode"] for i in items)
    assert not any(i["shot_id"] == "S??" for i in items)
    assert not any("downloads" in i["file_path"] for i in items)
    assert not any("开头样片" in i["file_path"] for i in items)
    assert not any("scene_shop" in i["file_path"] for i in items)
    assert not any("backdrop" in i["file_path"] for i in items)


def test_rescan_removes_unidentified_items_but_keeps_reviews(client, project):
    """历史脏卡片在重新扫描时被移除，已打分的正式镜头卡片原样保留。"""
    from app.database import SessionLocal
    from app.models import ShotReviewItem

    session = _create_session(client, project)
    items = _items(client, session["id"])
    target = next(
        i for i in items
        if i["shot_id"] == "EP01-S02" and i["file_path"].endswith(".mp4")
    )
    resp = client.patch(
        f"/api/v1/shot-reviews/items/{target['id']}",
        json={"score": 75, "feedback": "眼神再稳一点"},
    )
    assert resp.status_code == 200, resp.text

    # 模拟旧版本扫描残留的一条 S?? 母版卡片
    db = SessionLocal()
    try:
        base = db.get(ShotReviewItem, items[0]["id"])
        dirty = ShotReviewItem(**{
            column.name: getattr(base, column.name)
            for column in ShotReviewItem.__table__.columns
            if column.name != "id"
        })
        dirty.id = uuid.uuid4().hex
        dirty.episode = None
        dirty.shot_id = "S??"
        dirty.file_path = "08_成片制作/downloads/EP01/TG01_master.mp4"
        dirty.score = None
        dirty.feedback = ""
        dirty.sort_order = 99
        db.add(dirty)
        db.commit()
    finally:
        db.close()

    resp = client.post(f"/api/v1/shot-reviews/sessions/{session['id']}/scan")
    assert resp.status_code == 200, resp.text
    assert resp.json()["added"] == 0
    assert resp.json()["removed"] == 1

    after = _items(client, session["id"])
    assert len(after) == 4
    assert all(i["shot_id"] != "S??" for i in after)
    kept = next(i for i in after if i["id"] == target["id"])
    assert kept["score"] == 75
    assert kept["feedback"] == "眼神再稳一点"


def test_import_rejects_unidentified_rows(client, project):
    """导入接口与扫描同一道门禁：无集号/无镜号的行计入 skipped，不建空壳卡片。"""
    session = _create_session(client, project, scan=False)
    rows = [
        {
            "episode": "EP01",
            "shot_id": "EP01-S01",
            "file_path": "08_成片制作/EP01/video_renders/S01_seedance25/EP01-S01.mp4",
        },
        {
            "episode": None,
            "shot_id": "S??",
            "file_path": "08_成片制作/downloads/EP01/TG01_master.mp4",
        },
        {
            "episode": None,
            "shot_id": "S02",
            "file_path": "06_开头样片/clips_new/S02.mp4",
        },
    ]
    resp = client.post(
        f"/api/v1/shot-reviews/sessions/{session['id']}/items/import",
        json={"items": rows},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["added"] == 1
    assert result["skipped"] == 2
    assert [i["shot_id"] for i in _items(client, session["id"])] == ["EP01-S01"]
