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

"""SQLAlchemy 引擎与 Session 工厂。

- SQLite 默认开启 WAL 模式，提升并发写入能力。
- 提供 get_db 依赖注入；Celery Worker 中使用独立 Session 避免线程共享。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """ORM 基类。"""


def _build_engine(database_url: str) -> Engine:
    connect_args = {}
    is_sqlite = database_url.startswith("sqlite")

    if is_sqlite:
        # SQLite 需要禁用线程检查以允许 Celery 跨线程使用
        connect_args = {"check_same_thread": False}

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine: Engine = _build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# 用于引擎/会话重建（测试或运行时配置变更）
_engine_lock = threading.Lock()


def rebuild_engine() -> None:
    """在配置变化后重建引擎与 Session 工厂（主要用于测试）。"""
    global engine, SessionLocal
    with _engine_lock:
        engine.dispose()
        engine = _build_engine(settings.database_url)
        SessionLocal.configure(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每请求一个 Session，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Iterator[Session]:
    """同步上下文管理器：供 Celery Worker / 脚本使用。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_column(table: str, column: str, ddl_type: str) -> None:
    """为已有表补列（SQLite ALTER TABLE ADD COLUMN）。

    create_all 只能新建表，无法给已存在的表加列；线上库需要这种轻量迁移。
    仅在列缺失时执行，幂等。
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if not insp.has_table(table):
        return
    cols = [c["name"] for c in insp.get_columns(table)]
    if column in cols:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def _run_lightweight_migrations() -> None:
    """启动时执行的轻量级表结构补齐（无破坏性）。"""
    _ensure_column("tasks", "conversation_id", "TEXT")
    # 任务消耗 token 数（需求：任务中心展示模型与 token 信息）
    _ensure_column("tasks", "tokens_used", "INTEGER")
    # Seedance 参考素材审核字段（Spark Hub seedance_asset_audit）
    _ensure_column("assets", "audit_status", "TEXT")
    _ensure_column("assets", "audit_asset_id", "TEXT")
    _ensure_column("assets", "audit_asset_url", "TEXT")
    _ensure_column("assets", "audit_error", "TEXT")
    # 创作资产乐观锁同步字段（manifest v2 版本链）
    _ensure_column("creation_assets", "base_version", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column("creation_assets", "base_fingerprint", "TEXT NOT NULL DEFAULT ''")
    _ensure_column("creation_assets", "cloud_tag", "TEXT NOT NULL DEFAULT ''")


def init_db() -> None:
    """启动时建表（开发模式；生产应使用 Alembic 迁移）。"""
    from . import models  # noqa: F401  确保模型已注册

    settings.ensure_dirs()
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()
