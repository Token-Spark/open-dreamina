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

"""审片中心的导入接口：外部制作流程的分镜与生成结果 → 审片任务卡片。

覆盖三件事：不扫描的建会话、逐镜建档（含分镜「应有」与生成任务元信息）、
重复导入的幂等性（只刷新事实，不覆盖已打的分数与已写的意见）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings

_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def _shot_row(episode: str, shot_no: str, **overrides) -> dict:
    row = {
        "episode": episode,
        "shot_id": f"{episode}-{shot_no}",
        "drama_title": "圣诞男友",
        "file_path": f"08_成片制作/{episode}/video_renders/{shot_no}_seedance25/{episode}-{shot_no}.mp4",
        "duration": 4.01,
        "script_duration": 4.0,
        "shot_size": "中近景",
        "movement": "固定",
        "shot_function": "C1/B1｜母亲把南瓜派放进女儿盘里",
        "dialogue": 'MARIA: "We just want someone by your side."',
        "source_prompt": "【分镜】… · 【生成任务】EP01-TG01\n\nprompt body",
        "render_status": "completed",
        "model": "doubao_seedance_2_5",
    }
    row.update(overrides)
    return row


@pytest.fixture()
def drama_project(tmp_path, monkeypatch) -> Path:
    """造一个「08_成片制作/EPxx/video_renders/Sxx_*」布局的项目（不写分镜表）。"""
    root = tmp_path / "review_sources"
    project = root / "圣诞男友"
    for episode, shot_no in (("EP01", "S01"), ("EP01", "S02"), ("EP02", "S01")):
        target = project / "08_成片制作" / episode / "video_renders" / f"{shot_no}_seedance25"
        target.mkdir(parents=True)
        (target / f"{episode}-{shot_no}.mp4").write_bytes(_MP4)
    monkeypatch.setattr(settings, "review_source_roots", str(root))
    monkeypatch.setattr(settings, "shot_review_source_roots", str(root))
    return project


def _create_session(client, project: Path, *, title: str = "圣诞男友 S1 · 审片", scan: bool = False) -> dict:
    resp = client.post(
        f"/api/v1/shot-reviews/sessions?scan={'true' if scan else 'false'}",
        json={"title": title, "root_path": str(project)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _import(client, session_id: str, rows: list[dict]) -> dict:
    resp = client.post(
        f"/api/v1/shot-reviews/sessions/{session_id}/items/import",
        json={"items": rows},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _items(client, session_id: str) -> list[dict]:
    resp = client.get(f"/api/v1/shot-reviews/sessions/{session_id}/items")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_session_without_scan_stays_empty(client, drama_project):
    """导入流程建会话时不扫描：同目录下的参考素材不会被误收成审片条目。"""
    session = _create_session(client, drama_project)
    assert session["item_count"] == 0
    assert _items(client, session["id"]) == []


def test_import_builds_cards_with_storyboard_and_task_meta(client, drama_project):
    """导入后每镜一张卡片：分镜「应有」与生成任务「实际」一并落库，按集号+镜号排序。"""
    session = _create_session(client, drama_project)
    result = _import(client, session["id"], [
        _shot_row("EP02", "S01", drama_title="圣诞男友"),
        _shot_row("EP01", "S02"),
        _shot_row("EP01", "S01", input_asset_ids=["asset-a", "asset-b"]),
    ])
    assert result["added"] == 3
    assert result["updated"] == 0
    assert result["missing_count"] == 0

    items = _items(client, session["id"])
    assert [i["shot_id"] for i in items] == ["EP01-S01", "EP01-S02", "EP02-S01"]

    first = items[0]
    assert first["episode"] == "EP01"
    assert first["drama_title"] == "圣诞男友"
    assert first["script_duration"] == 4.0
    assert first["duration"] == 4.01
    assert first["shot_size"] == "中近景"
    assert first["movement"] == "固定"
    assert first["render_status"] == "completed"
    assert first["model"] == "doubao_seedance_2_5"
    assert "prompt body" in first["source_prompt"]
    assert first["origin"] == "scan"
    assert first["verdict"] == "pending"
    assert first["file_url"].endswith("/file")
    assert first["content_type"] == "video"
    # 原生成任务引用的资产：列表接口带回 id 与预览地址，供提示词编辑器展示
    assert first["input_asset_ids"] == ["asset-a", "asset-b"]
    assert first["input_asset_urls"] == [
        "/api/v1/assets/asset-a/file",
        "/api/v1/assets/asset-b/file",
    ]

    detail = client.get(f"/api/v1/shot-reviews/sessions/{session['id']}")
    assert detail.status_code == 200
    assert detail.json()["item_count"] == 3
    assert detail.json()["summary"]["pending"] == 3


def test_reimport_refreshes_meta_without_touching_review(client, drama_project):
    """重复导入幂等：刷新提示词/模型等事实，已打的分数与修改意见原样保留。"""
    session = _create_session(client, drama_project)
    _import(client, session["id"], [_shot_row("EP01", "S01")])
    item = _items(client, session["id"])[0]

    resp = client.patch(
        f"/api/v1/shot-reviews/items/{item['id']}",
        json={"score": 82, "feedback": "手部动作太抢，收一点"},
    )
    assert resp.status_code == 200, resp.text

    again = _import(client, session["id"], [
        _shot_row("EP01", "S01", source_prompt="新版提示词", model="doubao_seedance_2_6"),
    ])
    assert again["added"] == 0
    assert again["updated"] == 1
    assert again["total"] == 1

    refreshed = _items(client, session["id"])[0]
    assert refreshed["score"] == 82
    assert refreshed["feedback"] == "手部动作太抢，收一点"
    assert refreshed["source_prompt"] == "新版提示词"
    assert refreshed["model"] == "doubao_seedance_2_6"


def test_reimport_without_refs_keeps_existing_assets(client, drama_project):
    """重复导入不带参考素材字段时（--no-prompt / 旧清单）不覆盖已有 id 列表。"""
    session = _create_session(client, drama_project)
    _import(client, session["id"], [_shot_row("EP01", "S01", input_asset_ids=["a1", "a2"])])
    assert _items(client, session["id"])[0]["input_asset_ids"] == ["a1", "a2"]

    # 未带该字段：model_dump 给 None，import_items 跳过写入，保留原值
    _import(client, session["id"], [_shot_row("EP01", "S01")])
    assert _items(client, session["id"])[0]["input_asset_ids"] == ["a1", "a2"]

    # 显式传空列表是「该任务确无参考」的事实更新，允许清空
    _import(client, session["id"], [_shot_row("EP01", "S01", input_asset_ids=[])])
    assert _items(client, session["id"])[0]["input_asset_ids"] == []


def test_import_reports_missing_and_out_of_root_files(client, drama_project):
    """文件不存在或越界时不静默丢弃：计入 missing，其余条目照常建档。"""
    session = _create_session(client, drama_project)
    result = _import(client, session["id"], [
        _shot_row("EP01", "S01"),
        _shot_row("EP01", "S03", file_path="08_成片制作/EP01/video_renders/S03/EP01-S03.mp4"),
        _shot_row("EP02", "S09", file_path="../../escape.mp4"),
    ])

    assert result["added"] == 1
    assert result["missing_count"] == 2
    paths = {m["file_path"] for m in result["missing"]}
    assert "08_成片制作/EP01/video_renders/S03/EP01-S03.mp4" in paths
    assert "../../escape.mp4" in paths
    assert [i["shot_id"] for i in _items(client, session["id"])] == ["EP01-S01"]
