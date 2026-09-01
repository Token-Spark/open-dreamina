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
    # 多图生成：全部结果访问地址（单图时仅 1 项，与 result_url 首项一致）
    result_urls: list[str] = Field(default_factory=list)
    thumbnail_urls: list[str] = Field(default_factory=list)
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


class AssetAuditRequest(BaseModel):
    """提交 Seedance 参考素材审核：指定使用的 Provider slug（Spark Hub Seedance）。"""
    provider: str


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
    # Seedance 参考素材审核状态（Spark Hub seedance_asset_audit）
    audit_status: Optional[str] = None  # pending|active|failed
    audit_asset_id: Optional[str] = None
    audit_asset_url: Optional[str] = None  # 审核通过后的 asset:// 地址
    audit_error: Optional[str] = None
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


# ---------------- 创作资产（素材库） ----------------

class CreationAssetCreate(BaseModel):
    """新建创作资产。图片/音频先经 /assets/upload 上传，此处传 asset_id。"""
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field("character", pattern="^(character|scene|prop)$")
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    image_asset_id: Optional[str] = None
    audio_asset_id: Optional[str] = None


class CreationAssetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = Field(None, pattern="^(character|scene|prop)$")
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    image_asset_id: Optional[str] = None
    audio_asset_id: Optional[str] = None


class CreationAssetResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str
    image_asset_id: Optional[str] = None
    audio_asset_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    owner_id: str
    owner_name: str
    origin: str  # local|remote
    is_mine: bool  # owner_id == 本实例 owner_id（可信团队，remote 亦可编辑）
    synced_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # 乐观锁同步状态
    base_version: int = 0
    cloud_tag: str = ""
    has_pending_changes: bool = False  # 本地修改尚未推送（updated_at > synced_at 近似判断）
    # 便捷链接（关联媒体文件预览）
    image_url: Optional[str] = None
    image_thumbnail_url: Optional[str] = None
    audio_url: Optional[str] = None
    # 创建/编辑后即刻推送到云端的单资产同步结果（无推送则为 None）
    sync_result: Optional[dict] = None

    model_config = {"from_attributes": True}


class CreationAssetListResponse(BaseModel):
    items: list[CreationAssetResponse]
    total: int
    page: int
    page_size: int


class CreationAssetTagResponse(BaseModel):
    """标签汇总：驱动前端筛选与「按标签同步」入口。"""
    tags: list[dict] = Field(default_factory=list)  # [{name, count}]


class SyncConfigResponse(BaseModel):
    owner_id: str
    owner_name: str
    qiniu_configured: bool


class SyncConfigUpdate(BaseModel):
    owner_name: str = Field(..., min_length=1, max_length=50)


class TagSyncRequest(BaseModel):
    """按标签同步/拉取：tag 即云端一级目录（如短剧名称）。"""
    tag: str = Field(..., min_length=1, max_length=50)


class SyncResultItem(BaseModel):
    asset_id: str
    name: str
    status: str  # synced|conflict|failed|imported|updated|up_to_date|skipped
    version: Optional[int] = None
    message: Optional[str] = None


class SyncResultResponse(BaseModel):
    tag: str
    items: list[SyncResultItem]


# ---------------- 集中化自动同步 ----------------

class AutoSyncConfigResponse(BaseModel):
    """自动同步配置状态：enabled + 绑定的项目 tag + 最近同步时间。"""
    enabled: bool
    tag: str
    last_sync_at: str = ""


class AutoSyncConfigUpdate(BaseModel):
    """更新自动同步配置：开启时 tag 必填，关闭时 tag 可留空。"""
    enabled: bool
    tag: str = Field("", max_length=50)


class AutoSyncResultResponse(BaseModel):
    """手动触发一个自动同步周期的返回值。"""
    tag: str
    pushed: list[SyncResultItem]
    pulled: list[SyncResultItem]
    errors: list[str] = Field(default_factory=list)


# ---------------- 团队项目（云端目录 + project.json） ----------------

class ProjectCreate(BaseModel):
    """新建项目：项目即云端 team-assets/{tag}/ 目录。"""
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field("", max_length=500)


class ProjectMember(BaseModel):
    owner_id: str = ""
    owner_name: str = ""


class ProjectResponse(BaseModel):
    tag: str
    name: str
    description: str = ""
    created_by: str = ""
    created_by_id: str = ""
    created_at: str = ""
    members: list[ProjectMember] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]


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
    # 3D 导演台 iframe 地址；由 .env / 环境变量提供默认值，可在 settings 表覆盖。
    director_desk_url: str = ""


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


# ---------------- 画布工作流 ----------------

class CanvasCreate(BaseModel):
    """新建画布：可传初始文档或模板。"""
    name: Optional[str] = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    template_id: Optional[str] = None  # blank|single_image|img2video|storyboard
    document: Optional[dict[str, Any]] = None  # 直接传初始文档


class CanvasUpdate(BaseModel):
    """修改画布元数据。"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class CanvasSummary(BaseModel):
    """列表页卡片：不含文档体。"""
    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    conversation_id: Optional[str] = None
    cover_asset_id: Optional[str] = None
    cover_thumbnail_url: Optional[str] = None
    version: int = 1
    node_count: int = 0
    last_run_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class CanvasListResponse(BaseModel):
    items: list[CanvasSummary]
    total: int
    page: int
    page_size: int


class CanvasDocumentPayload(BaseModel):
    """画布文档 JSON 结构。"""
    schema_version: int = 1
    viewport: dict[str, Any] = Field(default_factory=lambda: {"x": 0, "y": 0, "zoom": 1})
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class CanvasDetail(BaseModel):
    """画布详情：元数据 + 最新文档 + 运行态投影。"""
    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    conversation_id: Optional[str] = None
    cover_asset_id: Optional[str] = None
    version: int = 1
    node_count: int = 0
    last_run_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    document: CanvasDocumentPayload
    runtime: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class CanvasDocumentResponse(BaseModel):
    """文档读接口返回：带 version。"""
    version: int
    document: CanvasDocumentPayload
    actor: str = "user"
    actor_name: str = ""
    change_summary: str = ""
    created_at: Optional[str] = None


class CanvasDocumentSave(BaseModel):
    """全量保存文档（乐观锁）。"""
    document: CanvasDocumentPayload
    base_version: int
    actor: str = "user"
    actor_name: str = ""
    change_summary: str = ""


class CanvasOperation(BaseModel):
    """单个原子操作。"""
    op: str  # add_node|remove_node|update_node_data|set_position|add_edge|remove_edge|reorder_edge|set_canvas_meta
    node: Optional[dict[str, Any]] = None
    node_id: Optional[str] = None
    edge: Optional[dict[str, Any]] = None
    edge_id: Optional[str] = None
    patch: Optional[dict[str, Any]] = None
    position: Optional[dict[str, float]] = None
    order: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class CanvasOperationsRequest(BaseModel):
    """增量原子操作请求。"""
    base_version: Optional[int] = None
    actor: str = "user"
    actor_name: str = ""
    change_summary: str = ""
    operations: list[CanvasOperation]


class CanvasOperationResult(BaseModel):
    version: int
    applied: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class CanvasValidationItem(BaseModel):
    level: str  # error|warning
    code: str
    message: str
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    fix: Optional[str] = None


class CanvasValidation(BaseModel):
    valid: bool
    errors: list[CanvasValidationItem] = Field(default_factory=list)
    warnings: list[CanvasValidationItem] = Field(default_factory=list)


class CanvasRunRequest(BaseModel):
    scope: str = Field("all", pattern="^(all|node|upstream)$")
    node_id: Optional[str] = None
    force: bool = False
    trigger: str = "user"  # user|agent


class CanvasRunCreateResponse(BaseModel):
    run_id: str


class CanvasRunSummary(BaseModel):
    """运行历史列表项。"""
    id: str
    canvas_id: str
    doc_version: int
    scope: str
    target_node_id: Optional[str] = None
    status: str
    trigger: str = "user"
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class CanvasRunListResponse(BaseModel):
    items: list[CanvasRunSummary]
    total: int
    page: int
    page_size: int


class CanvasRunDetail(BaseModel):
    id: str
    canvas_id: str
    doc_version: int
    scope: str
    target_node_id: Optional[str] = None
    status: str
    node_states: dict[str, Any] = Field(default_factory=dict)
    error_msg: Optional[str] = None
    trigger: str = "user"
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class CanvasVersionItem(BaseModel):
    version: int
    actor: str = "user"
    actor_name: str = ""
    change_summary: str = ""
    created_at: Optional[str] = None


class CanvasVersionListResponse(BaseModel):
    items: list[CanvasVersionItem]


class CanvasRevertRequest(BaseModel):
    target_version: int


class NodeSpecPort(BaseModel):
    id: str
    types: list[str] = Field(default_factory=list)
    multi: bool = False
    max: Optional[int] = None


class NodeSpec(BaseModel):
    inputs: list[NodeSpecPort] = Field(default_factory=list)
    outputs: list[NodeSpecPort] = Field(default_factory=list)


class NodeSpecResponse(BaseModel):
    specs: dict[str, NodeSpec]
