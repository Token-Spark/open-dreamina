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

"""资产业务服务：文件保存、缩略图、删除。"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Asset
from ..utils.file_utils import (
    SavedFile,
    delete_relative,
    make_thumbnail,
    resolve_relative,
)


def create_asset_record(
    db: Session,
    saved: SavedFile,
    task_id: str | None,
    asset_type: str,
    thumbnail_rel: str | None = None,
    tags: list[str] | None = None,
) -> Asset:
    import json
    asset = Asset(
        id=_new_uuid(),
        task_id=task_id,
        type=asset_type,
        file_path=saved.relative_path,
        thumbnail_path=thumbnail_rel,
        file_size=saved.file_size,
        mime_type=saved.mime_type,
        width=saved.width,
        height=saved.height,
        duration=saved.duration,
        tags_json=json.dumps(tags or [], ensure_ascii=False),
        is_favorite=0,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def generate_thumbnail_for(saved: SavedFile, asset_type: str) -> str | None:
    """生成缩略图，返回相对路径。失败返回 None。"""
    return make_thumbnail(saved.absolute_path, asset_type)


def delete_asset_files(asset: Asset) -> None:
    delete_relative(asset.file_path)
    if asset.thumbnail_path:
        delete_relative(asset.thumbnail_path)


def resolve_asset_path(asset: Asset, field: str = "file") -> Path | None:
    rel = asset.file_path if field == "file" else asset.thumbnail_path
    if not rel:
        return None
    p = resolve_relative(rel)
    return p if p.exists() else None


def _new_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
