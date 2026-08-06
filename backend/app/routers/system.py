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

"""系统路由：health + settings + backup + 即梦 CLI 引导。"""
from __future__ import annotations

import json
from datetime import datetime

import redis
from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Setting
from ..schemas import (
    BackupResponse,
    HealthResponse,
    MessageResponse,
    SystemSettings,
)
from ..services.backup_service import backup_database, list_backups
from ..worker import (
    celery_app,
    dreamina_cli_install_task,
    dreamina_cli_login_check_task,
    dreamina_cli_login_start_task,
    dreamina_cli_status_task,
)

router = APIRouter(prefix="/system", tags=["system"])

VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db_status = "down"
    redis_status = "down"
    worker_status = "down"

    # DB
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "down"

    # Redis
    try:
        r = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        redis_status = "ok"
        r.close()
    except Exception:
        redis_status = "down"

    # Worker：通过 celery inspect 探测在线节点
    try:
        inspector = celery_app.control.inspect(timeout=2)
        if inspector.ping():
            worker_status = "ok"
    except Exception:
        worker_status = "down"

    overall = "ok" if (db_status == "ok" and redis_status == "ok") else "degraded"
    if db_status == "down":
        overall = "down"

    return HealthResponse(
        status=overall,
        database=db_status,
        redis=redis_status,
        worker=worker_status,
        version=VERSION,
    )


@router.get("/settings", response_model=SystemSettings)
def get_settings(db: Session = Depends(get_db)) -> SystemSettings:
    items = {s.key: s.value for s in db.query(Setting).all()}
    # DB 无记录时回退到 config 默认值（环境变量 / .env），保证首次部署即可用。
    return SystemSettings(
        max_concurrent_tasks=int(items.get("max_concurrent_tasks", settings.max_concurrent_tasks)),
        default_provider=items.get("default_provider", ""),
    )


@router.put("/settings", response_model=SystemSettings)
def update_settings(
    payload: SystemSettings,
    db: Session = Depends(get_db),
) -> SystemSettings:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _upsert_setting(db, "max_concurrent_tasks", str(payload.max_concurrent_tasks), now)
    _upsert_setting(db, "default_provider", payload.default_provider, now)
    db.commit()
    return get_settings(db)


def _upsert_setting(db: Session, key: str, value: str, now: str) -> None:
    """插入或更新一条 settings 表记录。"""
    s = db.get(Setting, key)
    if s:
        s.value = value
        s.updated_at = now
    else:
        db.add(Setting(key=key, value=value, updated_at=now))


@router.post("/backup", response_model=BackupResponse)
def trigger_backup() -> BackupResponse:
    try:
        path = backup_database(keep_count=3)
        return BackupResponse(success=True, path=path, message="备份成功")
    except FileNotFoundError as e:
        raise HTTPException(status_code=409, detail={"code": "db_missing", "message": str(e)})
    except Exception as e:
        return BackupResponse(success=False, message=f"备份失败: {type(e).__name__}: {e}")


@router.get("/backups")
def get_backups():
    """列出已有备份文件。"""
    return {"items": list_backups()}


# ============================================================
# 即梦 CLI 安装 / 登录引导（均在 celery-worker 节点执行）
# ============================================================

def _run_worker_task(task, timeout: float, *args, offline_message: str, **kwargs):
    """分发任务到 worker 并同步等待结果；worker 不在线时返回带提示的降级结果。"""
    try:
        return task.apply_async(args=args, kwargs=kwargs).get(timeout=timeout)
    except CeleryTimeoutError:
        return {"worker_offline": True, "message": offline_message}
    except Exception as e:
        return {"worker_offline": True, "message": f"worker 任务执行异常：{type(e).__name__}: {e}"}


@router.get("/dreamina-cli/status")
def dreamina_cli_status(cli_path: str | None = None):
    """worker 节点上即梦 CLI 的安装 / 登录状态（前端引导页轮询）。"""
    return _run_worker_task(
        dreamina_cli_status_task,
        30,
        cli_path,
        offline_message="celery-worker 不在线，无法检测即梦 CLI 状态，请检查 worker 容器是否运行",
    )


@router.post("/dreamina-cli/install", response_model=MessageResponse)
def dreamina_cli_install():
    """触发 worker 节点安装即梦 CLI（异步执行，前端轮询 status 获取进度）。"""
    # 先置安装中标记，避免状态轮询在安装完成前显示「未安装」造成误导
    try:
        r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        r.set("dreamina_cli:installing", "1", ex=900)
    except Exception:
        pass
    dreamina_cli_install_task.delay()
    return MessageResponse(message="已开始安装即梦 CLI，请稍候（首次安装需下载二进制，可能耗时 1-2 分钟）")


@router.post("/dreamina-cli/login/start")
def dreamina_cli_login_start(cli_path: str | None = None):
    """发起 headless 登录，返回需用户在浏览器完成的授权材料。"""
    return _run_worker_task(
        dreamina_cli_login_start_task,
        120,
        cli_path,
        offline_message="celery-worker 不在线，无法发起即梦 CLI 登录",
    )


@router.get("/dreamina-cli/login/status")
def dreamina_cli_login_status(cli_path: str | None = None):
    """轮询登录授权是否完成（前端每几秒调用一次）。"""
    return _run_worker_task(
        dreamina_cli_login_check_task,
        60,
        cli_path,
        offline_message="celery-worker 不在线，无法检查登录状态",
    )
