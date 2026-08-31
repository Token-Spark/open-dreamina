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

"""创作资产（素材库）测试：CRUD、轻量资产校验、乐观锁版本链、三方合并与项目管理。"""
from __future__ import annotations

import json

from app.database import SessionLocal
from app.models import CreationAsset
from app.services import qiniu_service

API = "/api/v1/creation-assets"


def _create(client, **overrides):
    payload = {
        "name": "女主角-林小雨",
        "category": "character",
        "description": "18 岁，白衣，性格倔强",
        "tags": ["短剧A", "主角"],
    }
    payload.update(overrides)
    return client.post(API, json=payload)


# ---------------- CRUD ----------------

def test_create_and_get(client):
    resp = _create(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "女主角-林小雨"
    assert body["category"] == "character"
    assert body["origin"] == "local"
    assert body["is_mine"] is True
    assert body["base_version"] == 0
    assert body["cloud_tag"] == ""
    assert set(body["tags"]) == {"短剧A", "主角"}

    got = client.get(f"{API}/{body['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]


def test_create_with_media_ref_and_validation(client, uploaded_image):
    resp = _create(client, image_asset_id=uploaded_image)
    assert resp.status_code == 201
    assert resp.json()["image_asset_id"] == uploaded_image
    assert resp.json()["image_url"] == f"/api/v1/assets/{uploaded_image}/file"

    # 不存在的媒体引用应被拒绝（快速失败）
    bad = _create(client, image_asset_id="not-exist")
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "invalid_media_ref"


def test_video_media_ref_rejected(client):
    """轻量资产约束：视频类型媒体不允许关联（不同步视频）。"""
    resp = client.post(
        "/api/v1/assets/upload",
        files={"file": ("demo.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
    )
    assert resp.status_code == 201, resp.text
    video_asset_id = resp.json()["id"]

    bad = _create(client, image_asset_id=video_asset_id)
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "media_type_not_allowed"


def test_list_filters(client):
    _create(client, name="A1", tags=["短剧A"])
    _create(client, name="S1", category="scene", tags=["短剧B"])

    # 类别筛选
    resp = client.get(API, params={"category": "scene"})
    assert resp.status_code == 200
    assert [i["name"] for i in resp.json()["items"]] == ["S1"]

    # 标签筛选（任一命中）
    resp = client.get(API, params={"tags": "短剧A,不存在"})
    assert {i["name"] for i in resp.json()["items"]} == {"A1"}

    # 搜索
    resp = client.get(API, params={"search": "S1"})
    assert [i["name"] for i in resp.json()["items"]] == ["S1"]


def test_tags_summary(client):
    _create(client, name="A", tags=["短剧A", "主角"])
    _create(client, name="B", tags=["短剧A"])
    resp = client.get(f"{API}/tags")
    assert resp.status_code == 200
    tags = {t["name"]: t["count"] for t in resp.json()["tags"]}
    assert tags == {"短剧A": 2, "主角": 1}


def test_update_and_delete(client, uploaded_image):
    ca_id = _create(client, tags=["旧标签"]).json()["id"]

    resp = client.patch(
        f"{API}/{ca_id}",
        json={"name": "改名", "tags": ["新标签"], "image_asset_id": uploaded_image},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "改名"
    assert body["tags"] == ["新标签"]
    assert body["image_asset_id"] == uploaded_image

    resp = client.delete(f"{API}/{ca_id}")
    assert resp.status_code == 200
    assert client.get(f"{API}/{ca_id}").status_code == 404


def _seed_remote_asset(name: str = "他人资产") -> str:
    """直接向 DB 写入一条云端拉取的资产，模拟他人创建的数据。"""
    import uuid

    db = SessionLocal()
    try:
        ca = CreationAsset(
            id=uuid.uuid4().hex,
            name=name,
            category="prop",
            tags_json=json.dumps(["共享标签"], ensure_ascii=False),
            owner_id="someone-else",
            owner_name="别人",
            origin="remote",
        )
        db.add(ca)
        db.commit()
        return ca.id
    finally:
        db.close()


def test_remote_asset_is_editable(client):
    """可信团队模型：remote 资产同样可编辑（无只读限制）。"""
    ca_id = _seed_remote_asset()

    resp = client.patch(f"{API}/{ca_id}", json={"name": "帮忙改一下"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "帮忙改一下"

    resp = client.delete(f"{API}/{ca_id}")
    assert resp.status_code == 200


# ---------------- 云同步 / 拉取 ----------------

class FakeQiniu:
    """用内存 dict 模拟七牛云对象存储，校验 key 布局与内容。"""

    def __init__(self, monkeypatch):
        self.objects: dict[str, bytes] = {}
        monkeypatch.setattr(qiniu_service, "upload_team_object", self._upload)
        monkeypatch.setattr(qiniu_service, "list_team_keys", self._list)
        monkeypatch.setattr(qiniu_service, "list_all_team_keys", lambda: list(self.objects))
        monkeypatch.setattr(qiniu_service, "download_team_object", self._download)
        monkeypatch.setattr(qiniu_service, "try_download_team_object", self._try_download)

    def _upload(self, key: str, data: bytes) -> str:
        self.objects[key] = data
        return f"http://fake/{key}"

    def _list(self, tag: str) -> list[str]:
        prefix = f"team-assets/{tag}/"
        return [k for k in self.objects if k.startswith(prefix)]

    def _download(self, key: str) -> bytes:
        if key not in self.objects:
            raise RuntimeError(f"missing key: {key}")
        return self.objects[key]

    def _try_download(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def latest_manifest(self, tag: str, owner_id: str, asset_id: str) -> dict:
        key = qiniu_service.manifest_key(tag, owner_id, asset_id)
        return json.loads(self.objects[key])

    def put_latest_manifest(self, tag: str, owner_id: str, asset_id: str, manifest: dict) -> None:
        """模拟他人推送：写最新指针 + 历史版本。"""
        body = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        self.objects[qiniu_service.manifest_key(tag, owner_id, asset_id)] = body
        version = manifest.get("version") or 0
        if version:
            key = qiniu_service.versioned_manifest_key(tag, owner_id, asset_id, version)
            self.objects[key] = body


def _reset_local_assets():
    db = SessionLocal()
    db.query(CreationAsset).delete()
    db.commit()
    db.close()


def _get_local(ca_id: str) -> CreationAsset:
    db = SessionLocal()
    try:
        return db.get(CreationAsset, ca_id)
    finally:
        db.close()


def test_sync_builds_version_chain(client, monkeypatch, uploaded_image):
    """连续同步形成 append-only 版本链：manifest.1.json / manifest.2.json + 最新指针。"""
    fake = FakeQiniu(monkeypatch)
    mine = _create(client, name="同步资产", tags=["短剧A"], image_asset_id=uploaded_image).json()

    resp = client.post(f"{API}/sync", json={"tag": "短剧A"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["status"] == "synced"
    assert resp.json()["items"][0]["version"] == 1

    # 修改后再次同步 → v2，历史版本保留
    client.patch(f"{API}/{mine['id']}", json={"name": "同步资产-改"})
    resp = client.post(f"{API}/sync", json={"tag": "短剧A"})
    assert resp.json()["items"][0]["version"] == 2

    owner, asset_id = mine["owner_id"], mine["id"]
    v1 = json.loads(fake.objects[qiniu_service.versioned_manifest_key("短剧A", owner, asset_id, 1)])
    v2 = fake.latest_manifest("短剧A", owner, asset_id)
    assert v1["version"] == 1 and v1["name"] == "同步资产"
    assert v2["version"] == 2 and v2["name"] == "同步资产-改"
    assert v2["manifest_version"] == 2
    assert v2["fingerprint"] and v2["signature"]

    # 本地同步状态跟随云端版本
    local = _get_local(asset_id)
    assert local.base_version == 2
    assert local.cloud_tag == "短剧A"


def test_sync_rejects_when_cloud_ahead(client, monkeypatch):
    """CAS 乐观锁：云端版本领先于本地基线时拒绝推送，绝不盲覆盖。"""
    fake = FakeQiniu(monkeypatch)
    mine = _create(client, name="资产", tags=["短剧A"]).json()
    client.post(f"{API}/sync", json={"tag": "短剧A"})

    # 模拟他人在云端推了 v2
    cloud_v2 = fake.latest_manifest("短剧A", mine["owner_id"], mine["id"])
    cloud_v2["version"] = 2
    cloud_v2["name"] = "别人改的"
    fake.put_latest_manifest("短剧A", mine["owner_id"], mine["id"], cloud_v2)

    # 本地也改了 → 推送必须被拒绝
    client.patch(f"{API}/{mine['id']}", json={"name": "我改的"})
    resp = client.post(f"{API}/sync", json={"tag": "短剧A"})
    item = resp.json()["items"][0]
    assert item["status"] == "conflict"
    assert "请先拉取" in item["message"]

    # 云端内容未被覆盖
    assert fake.latest_manifest("短剧A", mine["owner_id"], mine["id"])["name"] == "别人改的"


def test_pull_fast_forward(client, monkeypatch):
    """三方合并-快进：本地未改、云端更新 → 直接更新本地。"""
    fake = FakeQiniu(monkeypatch)
    mine = _create(client, name="资产", tags=["短剧A"]).json()
    client.post(f"{API}/sync", json={"tag": "短剧A"})

    # 模拟他人推送 v2（保持签名有效：重算走不到，签名校验失败仅提示，不阻断快进）
    cloud_v2 = fake.latest_manifest("短剧A", mine["owner_id"], mine["id"])
    cloud_v2["version"] = 2
    cloud_v2["description"] = "云端补充的描述"
    fake.put_latest_manifest("短剧A", mine["owner_id"], mine["id"], cloud_v2)

    resp = client.post(f"{API}/pull", json={"tag": "短剧A"})
    item = resp.json()["items"][0]
    assert item["status"] == "updated"
    assert item["version"] == 2

    local = _get_local(mine["id"])
    assert local.base_version == 2
    assert local.description == "云端补充的描述"


def test_pull_conflict_keeps_both(client, monkeypatch):
    """三方合并-冲突：本地与云端都改了 → 云端版导入为副本，本地不丢。"""
    fake = FakeQiniu(monkeypatch)
    mine = _create(client, name="我的版本", tags=["短剧A"]).json()
    client.post(f"{API}/sync", json={"tag": "短剧A"})

    cloud_v2 = fake.latest_manifest("短剧A", mine["owner_id"], mine["id"])
    cloud_v2["version"] = 2
    cloud_v2["name"] = "云端版本"
    fake.put_latest_manifest("短剧A", mine["owner_id"], mine["id"], cloud_v2)

    # 本地也修改（未推送）
    client.patch(f"{API}/{mine['id']}", json={"name": "本地版本"})

    resp = client.post(f"{API}/pull", json={"tag": "短剧A"})
    item = resp.json()["items"][0]
    assert item["status"] == "conflict"
    assert "副本" in item["message"]

    # 本地原资产保留本地修改，云端版以副本形式存在（副本名基于本地当前名）
    names = {i["name"] for i in client.get(API).json()["items"]}
    assert names == {"本地版本", "本地版本（云端 v2）"}

    # 副本基于云端 v2
    copy_id = [i for i in client.get(API).json()["items"] if "云端" in i["name"]][0]["id"]
    copy = _get_local(copy_id)
    assert copy.base_version == 2


def test_pull_flags_tampered_signature(client, monkeypatch):
    """签名校验：指纹被篡改的 manifest 不拒收，但结果标记来源可疑。"""
    fake = FakeQiniu(monkeypatch)
    mine = _create(client, name="资产", tags=["短剧A"]).json()
    client.post(f"{API}/sync", json={"tag": "短剧A"})

    # 篡改云端内容但不更新签名
    tampered = fake.latest_manifest("短剧A", mine["owner_id"], mine["id"])
    tampered["version"] = 2
    tampered["description"] = "被篡改的内容"
    fake.put_latest_manifest("短剧A", mine["owner_id"], mine["id"], tampered)

    resp = client.post(f"{API}/pull", json={"tag": "短剧A"})
    item = resp.json()["items"][0]
    assert item["status"] == "updated"
    assert "来源可疑" in (item["message"] or "")


def test_sync_then_pull_roundtrip(client, monkeypatch, uploaded_image, png_bytes):
    fake = FakeQiniu(monkeypatch)

    mine = _create(client, name="同步资产", tags=["短剧A"], image_asset_id=uploaded_image).json()
    _create(client, name="别的标签", tags=["短剧B"])

    resp = client.post(f"{API}/sync", json={"tag": "短剧A"})
    assert resp.status_code == 200, resp.text
    items = {i["asset_id"]: i for i in resp.json()["items"]}
    assert items[mine["id"]]["status"] == "synced"
    # 只有「短剧A」下我的资产被同步
    assert fake.objects.keys() >= {f"team-assets/短剧A/{mine['owner_id']}/{mine['id']}/manifest.json"}
    assert not any("短剧B" in k for k in fake.objects)

    # 清空本地创作资产，模拟另一用户拉取
    _reset_local_assets()

    resp = client.post(f"{API}/pull", json={"tag": "短剧A"})
    assert resp.status_code == 200, resp.text
    imported = [i for i in resp.json()["items"] if i["status"] == "imported"]
    assert len(imported) == 1

    pulled = client.get(API, params={"tags": "短剧A"}).json()["items"][0]
    assert pulled["name"] == "同步资产"
    assert pulled["origin"] == "remote"
    # 同一实例拉回自己推送的资产：owner 相同 → is_mine 为 True
    assert pulled["is_mine"] is True
    assert pulled["image_asset_id"] is not None
    # 拉取的图片可正常访问
    img = client.get(pulled["image_url"])
    assert img.status_code == 200
    assert img.content == png_bytes

    # 再次拉取：本地已有（同 id 且内容一致），已是最新
    resp = client.post(f"{API}/pull", json={"tag": "短剧A"})
    statuses = [i["status"] for i in resp.json()["items"]]
    assert "imported" not in statuses
    assert "up_to_date" in statuses


def test_sync_no_matching_tag_fails_fast(client, monkeypatch):
    FakeQiniu(monkeypatch)
    resp = client.post(f"{API}/sync", json={"tag": "不存在"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "sync_failed"


def test_sync_owner_isolation(client, monkeypatch):
    """两个用户先后同步同一标签：key 按 owner 分目录，互不覆盖。"""
    fake = FakeQiniu(monkeypatch)

    first = _create(client, name="用户1资产", tags=["共享"]).json()
    client.post(f"{API}/sync", json={"tag": "共享"})

    # 模拟另一台机器（不同 owner、没有用户1的本地数据）
    from app.models import Setting
    db = SessionLocal()
    db.query(CreationAsset).delete()
    db.query(Setting).filter(Setting.key == "creation_asset_owner_id").update(
        {"value": "user-two"}
    )
    db.commit()
    db.close()

    second = _create(client, name="用户2资产", tags=["共享"]).json()
    resp = client.post(f"{API}/sync", json={"tag": "共享"})
    assert resp.status_code == 200

    keys = fake.objects
    first_keys = [k for k in keys if f"/{first['id']}/" in k]
    second_keys = [k for k in keys if f"/{second['id']}/" in k]
    assert all(f"/{first['owner_id']}/" in k for k in first_keys)
    assert all("/user-two/" in k for k in second_keys)
    assert first_keys and second_keys

    # 用户2拉取该标签：能同时拿到用户1与自己的资产
    _reset_local_assets()
    resp = client.post(f"{API}/pull", json={"tag": "共享"})
    assert resp.status_code == 200
    imported = {i["name"] for i in resp.json()["items"] if i["status"] == "imported"}
    assert imported == {"用户1资产", "用户2资产"}


# ---------------- 项目管理 ----------------

def test_project_create_and_list(client, monkeypatch):
    fake = FakeQiniu(monkeypatch)

    resp = client.post(f"{API}/projects", json={"name": "短剧A", "description": "都市题材"})
    assert resp.status_code == 201, resp.text
    project = resp.json()
    assert project["tag"] == "短剧A"
    assert project["members"] and project["members"][0]["owner_id"]

    # 云端写入 project.json
    key = qiniu_service.project_key("短剧A")
    assert key in fake.objects
    assert json.loads(fake.objects[key])["name"] == "短剧A"

    # 重名项目拒绝（快速失败）
    dup = client.post(f"{API}/projects", json={"name": "短剧A"})
    assert dup.status_code == 400
    assert dup.json()["detail"]["code"] == "project_create_failed"

    # 项目列表可见
    resp = client.get(f"{API}/projects")
    assert resp.status_code == 200
    tags = [p["tag"] for p in resp.json()["items"]]
    assert "短剧A" in tags


def test_sync_updates_project_members(client, monkeypatch):
    """同步时顺带更新成员名册：项目不存在则补建，成员去重。"""
    fake = FakeQiniu(monkeypatch)
    _create(client, name="资产", tags=["新项目"])

    client.post(f"{API}/sync", json={"tag": "新项目"})
    # 同步自动补建 project.json 并登记成员
    key = qiniu_service.project_key("新项目")
    assert key in fake.objects
    members = json.loads(fake.objects[key])["members"]
    assert len(members) == 1

    # 再次同步不重复登记
    client.post(f"{API}/sync", json={"tag": "新项目"})
    members = json.loads(fake.objects[key])["members"]
    assert len(members) == 1
