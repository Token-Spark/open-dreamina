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

"""剧集镜头审片的请求/响应模型。

独立成模块，与 schemas.py 分离，避免该文件继续膨胀。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ShotReviewSessionCreate(BaseModel):
    """新建审片会话：指定标题与要扫描的剧集视频根目录。"""

    title: str = Field(..., min_length=1, max_length=200)
    root_path: str = Field(..., min_length=1)


class ShotReviewSessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    status: Optional[str] = Field(None, pattern="^(draft|in_review|completed|archived)$")


class ShotReviewItemResponse(BaseModel):
    id: str
    session_id: str
    episode: Optional[str] = None
    shot_id: str
    file_path: str
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    thumbnail_path: Optional[str] = None
    score: Optional[int] = None
    verdict: str = "pending"  # pending|pass|revise|redesign
    feedback: str = ""
    # 同镜号多版本时的「选定保留版本」标记；同一集+镜号下至多一条为 True
    selected: bool = False
    source_prompt: Optional[str] = None
    revised_prompt: Optional[str] = None
    shot_function: Optional[str] = None
    script_duration: Optional[float] = None
    shot_size: Optional[str] = None
    movement: Optional[str] = None
    dialogue: Optional[str] = None
    render_status: Optional[str] = None
    model: Optional[str] = None
    sort_order: int = 0
    reviewed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ShotReviewSessionResponse(BaseModel):
    id: str
    title: str
    root_path: str
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    item_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ShotReviewSessionListResponse(BaseModel):
    items: list[ShotReviewSessionResponse]
    total: int


class ShotReviewItemUpdate(BaseModel):
    """更新单个审片条目：打分（0–100）、修改意见、精修提示词与选定标记。

    clear_score=True 时清除评分（回到待审）。
    revised_prompt 为审片人改写的 AIGC 提示词，作为该镜的修改备注；
    传 None 不修改，传空串表示清除。
    selected=True 选定该版本为同镜号栏目的保留版本（同组其余自动取消）。
    """

    score: Optional[int] = Field(None, ge=0, le=100)
    clear_score: bool = False
    feedback: Optional[str] = None
    revised_prompt: Optional[str] = None
    selected: Optional[bool] = None


class ShotReviewBatchUpdateItem(BaseModel):
    id: str
    score: Optional[int] = Field(None, ge=0, le=100)
    clear_score: bool = False
    feedback: Optional[str] = None
    revised_prompt: Optional[str] = None
    selected: Optional[bool] = None


class ShotReviewBatchUpdateRequest(BaseModel):
    items: list[ShotReviewBatchUpdateItem]


class ShotReviewBatchUpdateResponse(BaseModel):
    updated: int
    failed: int = 0


class ShotReviewBulkDeleteRequest(BaseModel):
    """批量删除审片条目（通常为同镜号下未选定的废弃版本）。

    delete_file=True 时同时从磁盘删除对应视频文件；False 仅移出审片列表。
    """

    item_ids: list[str] = Field(..., min_length=1)
    delete_file: bool = False


class ShotReviewBulkDeleteResponse(BaseModel):
    deleted: int
    failed: int = 0
    freed_bytes: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class ShotReviewFolderListResponse(BaseModel):
    """列出允许根目录下的可选子文件夹，供前端选择扫描目标。"""

    roots: list[dict[str, Any]]


class ShotReviewScanResponse(BaseModel):
    """重新扫描后新增/移除的条目统计。"""

    added: int = 0
    removed: int = 0
    total: int = 0