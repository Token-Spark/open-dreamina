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

"""测试夹具：导入 app 前强制环境变量指向临时目录，隔离真实数据。"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

# 必须在导入 app 模块之前设置（config/database 均为模块级单例）
_TMP = Path(tempfile.mkdtemp(prefix="od-ca-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["ASSETS_DIR"] = (_TMP / "assets").as_posix()
os.environ["BACKUP_DIR"] = (_TMP / "backups").as_posix()
os.environ["ENCRYPTION_KEY"] = "test-only-key"
# 模拟已配置七牛云（同步测试中会 monkeypatch 网络函数）
os.environ["QINIU_ACCESS_KEY"] = "test-ak"
os.environ["QINIU_SECRET_KEY"] = "test-sk"
os.environ["QINIU_BUCKET"] = "test-bucket"
os.environ["QINIU_DOMAIN"] = "http://test.domain.clouddn.com"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_tables():
    """每个测试前清空相关表，保证断言不受先前测试数据影响。"""
    from app.database import SessionLocal, init_db
    from app.models import Asset, CreationAsset, Setting

    init_db()
    db = SessionLocal()
    try:
        db.query(CreationAsset).delete()
        db.query(Asset).delete()
        db.query(Setting).filter(Setting.key.like("creation_asset_%")).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture()
def client():
    """每个测试独立的 TestClient（startup 触发 init_db 建表）。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def png_bytes() -> bytes:
    """1x1 PNG 测试图。"""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def uploaded_image(client, png_bytes) -> str:
    """通过 /assets/upload 上传测试图片，返回 asset_id。"""
    resp = client.post(
        "/api/v1/assets/upload",
        files={"file": (f"{uuid.uuid4().hex}.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
