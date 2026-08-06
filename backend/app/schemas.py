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

"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------- 任务 ----------------

class TaskCreate(BaseModel):
    type: str = Field(..., description="text2img|img2img|text2video|img2video")
    provider: str
    model_id: Optional[str] = None
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    input_asset_id: Optional[str] = None
    # 多图参考：上传多张参考图时传入完整列表。
    # 首张仍写入 input_asset_id（兼容旧逻辑/预览派生），完整列表存入 params.input_asset_ids。
    input_asset_ids: Optional[list[str]] = None
    conversation_id: Optional[str] = None


class TaskCreateResponse(BaseModel):
    """POST /tasks 返回：仅 task_id（符合规格 5.1）。"""
    task_id: str


class TaskParams(BaseModel):
    """常用生成参数（仅用于文档化，实际参数以 params dict 为准）。"""
    negative_prompt: Optional[str] = None
    width: int = 1024
    height: int = 1024
    steps: int = 30
    guidance_scale: float = 7.0
    seed: Optional[int] = None
    duration: int = 5


class TaskResponse(BaseModel):
    id: str
    type: str
    status: str
    progress: int
    provider: str
    model_id: Optional[str] = None
    prompt: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    input_asset_id: Optional[str] = None
    # 输入参考图的访问地址（由 input_asset_id 派生，便于前端复用回填预览）
    input_asset_url: Optional[str] = None
    result_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    result_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    error_msg: Optional[str] = None
    api_cost: Optional[float] = None
    # 该任务消耗的 token 数（由 Provider 元数据回填，可能为 None）
    tokens_used: Optional[int] = None
    retry_count: int = 0
    conversation_id: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    page: int
    page_size: int


# ---------------- 对话 ----------------

class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0
    last_prompt: Optional[str] = None
    last_thumbnail_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int


# ---------------- 资产 ----------------

class AssetUpdate(BaseModel):
    tags: Optional[list[str]] = None
    is_favorite: Optional[bool] = None


class AssetResponse(BaseModel):
    id: str
    task_id: Optional[str] = None
    type: str
    file_path: str
    thumbnail_path: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    tags: list[str] = Field(default_factory=list)
    is_favorite: bool = False
    created_at: Optional[str] = None
    # 便捷链接
    file_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    page: int
    page_size: int


class BatchDeleteRequest(BaseModel):
    asset_ids: list[str]


class BatchDeleteResponse(BaseModel):
    deleted: list[str]
    failed: list[str]


# ---------------- Provider ----------------

class ProviderCreate(BaseModel):
    name: str
    slug: str
    base_url: str
    api_key: str
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[dict[str, Any]] = None


class ProviderResponse(BaseModel):
    id: str
    name: str
    slug: str
    base_url: str
    api_key_masked: str
    is_active: bool
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ProviderTestResult(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None


class ProviderSlugOption(BaseModel):
    """可用 slug 元信息：驱动前端「添加自定义服务」下拉选择。"""
    slug: str
    display_name: str
    modes: list[str]  # "image" | "video"
    default_base_url: str
    builtin: bool


class ProviderTestBeforeCreate(BaseModel):
    """新建前连通性测试入参：无需先落库即可测试。"""
    slug: str
    base_url: str
    api_key: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class ProviderTestOverride(BaseModel):
    """按 id 测试时的可选覆盖项：用表单当前值测试未保存的改动。

    - base_url / api_key / config 任一未提供则回退到已落库值。
    - api_key 留空时后端使用已加密的旧 Key，避免泄露或重复输入。
    """
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    config: Optional[dict[str, Any]] = None


# ---------------- 模板 ----------------

class TemplateCreate(BaseModel):
    name: str
    category: str = "image"  # image|video
    prompt_text: str
    negative_prompt: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    prompt_text: Optional[str] = None
    negative_prompt: Optional[str] = None
    params: Optional[dict[str, Any]] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    prompt_text: str
    negative_prompt: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    preview_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------- 系统 ----------------

class HealthResponse(BaseModel):
    status: str  # ok|degraded|down
    database: str  # ok|down
    redis: str  # ok|down
    worker: str  # ok|unknown|down
    version: str = "0.1.0"


class SystemSettings(BaseModel):
    """系统设置：扁平结构，与前端 SystemSettings 接口对齐。
    持久化于 settings 表；GET 缺省值由路由层从 config 合并。"""
    max_concurrent_tasks: int = Field(default=2, ge=1, le=8)
    default_provider: str = ""


class BackupResponse(BaseModel):
    success: bool
    path: Optional[str] = None
    message: Optional[str] = None


# ---------------- 通用 ----------------

class ErrorResponse(BaseModel):
    error: dict[str, Any]


class MessageResponse(BaseModel):
    message: str
    detail: Optional[Any] = None
