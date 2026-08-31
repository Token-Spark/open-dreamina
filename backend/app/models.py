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

"""ORM 模型，严格对应规格书第 4 节 SQL 定义。"""
from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .utils.time_utils import now_iso as _now_iso


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="新对话")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)

    tasks: Mapped[list["Task"]] = relationship(
        "Task", back_populates="conversation", passive_deletes=True
    )

    __table_args__ = (Index("idx_conversations_created", "created_at"),)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # text2img|img2img|text2video|img2video
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    input_asset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 该任务消耗的 token 数（由 Provider 元数据回填；mock 也会模拟一个值便于联调展示）
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversation_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    assets: Mapped[list["Asset"]] = relationship(
        "Asset", back_populates="task", passive_deletes=True
    )
    conversation: Mapped["Conversation | None"] = relationship(
        "Conversation", back_populates="tasks"
    )

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_created", "created_at"),
        Index("idx_tasks_conversation", "conversation_id"),
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False)  # image|video|audio
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_favorite: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Seedance 参考素材审核（Spark Hub seedance_asset_audit）：
    # audit_status: pending|active|failed；audit_asset_url 为审核通过后的 asset:// 地址。
    audit_status: Mapped[str | None] = mapped_column(String, nullable=True)
    audit_asset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    audit_asset_url: Mapped[str | None] = mapped_column(String, nullable=True)
    audit_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)

    task: Mapped[Task | None] = relationship("Task", back_populates="assets")

    __table_args__ = (
        Index("idx_assets_type", "type"),
        Index("idx_assets_created", "created_at"),
    )


class CreationAsset(Base):
    """创作资产：人物/场景/道具等可复用素材，聚合图片、音色音频与文本设定。

    - origin=local：本实例创建，可编辑/删除/同步；
      origin=remote：从云端拉取的他人资产，本地只读，可另存为副本。
    - owner_id 用于云同步权限隔离：云端对象 key 按创建者分目录，互不覆盖。
    """

    __tablename__ = "creation_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # character|scene|prop
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_asset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    audio_asset_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    owner_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    origin: Mapped[str] = mapped_column(String, nullable=False, default="local")  # local|remote
    synced_at: Mapped[str | None] = mapped_column(String, nullable=True)
    # 乐观锁同步状态：上次推送/拉取时的云端版本与内容指纹快照。
    # base_version=0 表示从未同步；指纹与当前内容不一致即「有未推送修改」。
    base_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_fingerprint: Mapped[str] = mapped_column(String, nullable=False, default="")
    # 上次同步所在的云端标签目录（项目），推送回写同一位置
    cloud_tag: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)

    image_asset: Mapped[Asset | None] = relationship("Asset", foreign_keys=[image_asset_id])
    audio_asset: Mapped[Asset | None] = relationship("Asset", foreign_keys=[audio_asset_id])

    __table_args__ = (
        Index("idx_creation_assets_category", "category"),
        Index("idx_creation_assets_created", "created_at"),
    )


class ApiProvider(Base):
    __tablename__ = "api_providers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_enc: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # image|video
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    preview_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=_now_iso)
