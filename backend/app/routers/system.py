"""系统路由：health + settings + backup。"""
from __future__ import annotations

import json
from datetime import datetime

import redis
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
    SettingsResponse,
    SettingsUpdate,
)
from ..services.backup_service import backup_database, list_backups

router = APIRouter(prefix="/system", tags=["system"])

VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db_status = "down"
    redis_status = "down"
    worker_status = "unknown"

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
        # 简单判断 worker：查询是否有 inspect 响应（轻量探测 celery 在线）
        # 此处仅做 Redis 可达性判断；Worker 深度检查需 celery inspect，依赖较重，暂标记 unknown
        r.close()
    except Exception:
        redis_status = "down"

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


@router.get("/settings", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)) -> SettingsResponse:
    items = db.query(Setting).all()
    return SettingsResponse(settings={s.key: s.value for s in items})


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
) -> SettingsResponse:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for k, v in payload.settings.items():
        s = db.get(Setting, k)
        if s:
            s.value = v
            s.updated_at = now
        else:
            db.add(Setting(key=k, value=v, updated_at=now))
    db.commit()
    items = db.query(Setting).all()
    return SettingsResponse(settings={s.key: s.value for s in items})


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
