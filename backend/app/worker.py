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

"""Celery 实例 + 任务定义。

- run_generation_task: 调用 Provider 执行生成；进度节点 10/30/60/100。
- backup_database_task: 定时数据库备份。
"""
from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import datetime
from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

from .config import settings
from .database import db_session
from .models import ApiProvider, Asset, Task
from .providers import ProviderError, get_provider
from .services import task_service
from .services.asset_service import (
    create_asset_record,
    delete_asset_files,
    generate_thumbnail_for,
)
from .services.backup_service import backup_database
from .utils.crypto import decrypt
from .utils.file_utils import resolve_relative, save_uploaded_file

logger = logging.getLogger(__name__)

celery_app = Celery(
    "aigc_studio",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.task_time_limit,
    task_soft_time_limit=settings.task_soft_time_limit,
    beat_schedule={
        "daily-db-backup": {
            "task": "app.worker.backup_database_task",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _update_task(
    task_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    error_msg: str | None = None,
    result_path: str | None = None,
    thumbnail_path: str | None = None,
    tokens_used: int | None = None,
    api_cost: float | None = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    """更新任务记录（独立 Session，避免与其它写入冲突）。"""
    with db_session() as db:
        task = db.get(Task, task_id)
        if not task:
            logger.warning("Task %s not found", task_id)
            return
        if status is not None:
            task.status = status
        if progress is not None:
            task.progress = progress
        if error_msg is not None:
            task.error_msg = error_msg
        if result_path is not None:
            task.result_path = result_path
        if thumbnail_path is not None:
            task.thumbnail_path = thumbnail_path
        if tokens_used is not None:
            task.tokens_used = tokens_used
        if api_cost is not None:
            task.api_cost = api_cost
        if started:
            task.started_at = _now()
        if completed:
            task.completed_at = _now()


def _persist_submit_id(task_id: str, submit_id: str) -> None:
    """把已提交的上游任务 ID 合并进 params_json 落库，供 retry 断点续查（不覆盖其它参数）。"""
    with db_session() as db:
        task = db.get(Task, task_id)
        if not task:
            return
        params: dict[str, Any] = json.loads(task.params_json or "{}")
        params["submit_id"] = submit_id
        task.params_json = json.dumps(params, ensure_ascii=False)


def _extract_tokens(metadata: dict[str, Any]) -> int | None:
    """从 Provider 返回的 metadata 中提取 token 用量。

    兼容多种字段命名：tokens_used / total_tokens / usage.total_tokens。
    """
    if not metadata:
        return None
    for key in ("tokens_used", "total_tokens", "tokens"):
        v = metadata.get(key)
        if isinstance(v, (int, float)) and v >= 0:
            return int(v)
    usage = metadata.get("usage")
    if isinstance(usage, dict):
        for key in ("total_tokens", "tokens_used"):
            v = usage.get(key)
            if isinstance(v, (int, float)) and v >= 0:
                return int(v)
    return None


def _read_input_asset_bytes(input_asset_id: str) -> bytes | None:
    with db_session() as db:
        a = db.get(Asset, input_asset_id)
        if not a:
            return None
        p = resolve_relative(a.file_path)
        if not p.exists():
            return None
        return p.read_bytes()


def _read_input_asset_bytes_list(asset_ids: list[str]) -> list[bytes]:
    """读取多张参考图的原始字节（跳过读取失败的资产）。"""
    out: list[bytes] = []
    for aid in asset_ids:
        b = _read_input_asset_bytes(aid)
        if b is not None:
            out.append(b)
    return out


@celery_app.task(name="app.worker.run_generation_task", bind=True)
def run_generation_task(self, task_id: str) -> dict[str, Any]:  # noqa: ANN001
    """执行生成任务。"""
    # 1. 标记 started (10%)
    _update_task(task_id, status="running", progress=10, started=True)
    task_service.set_progress(task_id, "running", 10, "任务已开始")

    try:
        with db_session() as db:
            task = db.get(Task, task_id)
            if not task:
                return {"task_id": task_id, "error": "task not found"}
            task_type = task.type
            prompt = task.prompt or ""
            params: dict[str, Any] = json.loads(task.params_json or "{}")
            input_asset_id = task.input_asset_id
            provider_slug = task.provider
            model_id = task.model_id

        # 检查取消
        if task_service.is_cancelled(task_id):
            _update_task(task_id, status="cancelled", completed=True)
            task_service.clear_progress(task_id)
            return {"task_id": task_id, "status": "cancelled"}

        provider, slug = _load_provider_for_task_via_db(task_id)

        # 2. generating 30%
        task_service.set_progress(task_id, "running", 30, "正在生成中…")
        _update_task(task_id, progress=30)

        if task_service.is_cancelled(task_id):
            _update_task(task_id, status="cancelled", completed=True)
            task_service.clear_progress(task_id)
            return {"task_id": task_id, "status": "cancelled"}

        kwargs: dict[str, Any] = {}
        if model_id:
            kwargs["model_id"] = model_id
        # 透传常用参数
        for k in ("negative_prompt", "width", "height", "steps", "guidance_scale", "seed", "duration", "strength"):
            if k in params:
                kwargs[k] = params[k]
        # 断点续查：上一轮失败后落库的 submit_id 透传给 provider，避免重新 submit 重复扣费
        if params.get("submit_id"):
            kwargs["submit_id"] = params["submit_id"]

        # 参考图：优先从 params.input_asset_ids 读取多图列表，回退到 input_asset_id 单图
        raw_ids: list[str] = []
        param_ids = params.get("input_asset_ids")
        if isinstance(param_ids, list):
            raw_ids = [aid for aid in param_ids if isinstance(aid, str) and aid]
        if not raw_ids and input_asset_id:
            raw_ids = [input_asset_id]

        image_bytes_list: list[bytes] = []
        if task_type in ("img2img", "img2video") and raw_ids:
            image_bytes_list = _read_input_asset_bytes_list(raw_ids)

        loop = asyncio.new_event_loop()
        try:
            if task_type == "text2img":
                result = loop.run_until_complete(provider.text_to_image(prompt=prompt, **_filter_kwargs(provider.text_to_image, kwargs)))
            elif task_type == "img2img":
                if not image_bytes_list:
                    raise ProviderError("图生图缺少输入图片")
                result = loop.run_until_complete(provider.image_to_image(image_bytes=image_bytes_list, prompt=prompt, **_filter_kwargs(provider.image_to_image, kwargs)))
            elif task_type == "text2video":
                result = loop.run_until_complete(provider.text_to_video(prompt=prompt, **_filter_kwargs(provider.text_to_video, kwargs)))
            elif task_type == "img2video":
                # 视频生成仅取首张参考图（多图视频暂未接入）
                first_bytes = image_bytes_list[0] if image_bytes_list else None
                if first_bytes is None:
                    raise ProviderError("图生视频缺少输入图片")
                result = loop.run_until_complete(provider.image_to_video(image_bytes=first_bytes, prompt=prompt, **_filter_kwargs(provider.image_to_video, kwargs)))
            else:
                raise ProviderError(f"未知任务类型: {task_type}")
        finally:
            loop.close()

        # 3. 60% 后处理中
        task_service.set_progress(task_id, "running", 60, "正在保存结果…")
        _update_task(task_id, progress=60)

        if task_service.is_cancelled(task_id):
            _update_task(task_id, status="cancelled", completed=True)
            task_service.clear_progress(task_id)
            return {"task_id": task_id, "status": "cancelled"}

        # 保存文件
        from .utils.file_utils import save_generated_file
        saved = save_generated_file(result.file_bytes, result.mime_type)

        # 生成缩略图
        asset_type = "image" if result.mime_type.startswith("image/") else "video"
        thumb_rel = generate_thumbnail_for(saved, asset_type)

        # 写资产记录
        with db_session() as db:
            asset = create_asset_record(
                db=db,
                saved=saved,
                task_id=task_id,
                asset_type=asset_type,
                thumbnail_rel=thumb_rel,
                tags=[],
            )
            asset_id = asset.id

        # 从 Provider 元数据提取 token 用量与费用，回填任务记录（需求：任务中心展示 token 信息）
        tokens_used = _extract_tokens(result.metadata)
        api_cost = result.metadata.get("api_cost") if isinstance(result.metadata, dict) else None
        if isinstance(api_cost, (int, float)) and api_cost >= 0:
            api_cost = float(api_cost)
        else:
            api_cost = None

        # 4. 100% completed
        _update_task(
            task_id,
            status="completed",
            progress=100,
            result_path=saved.relative_path,
            thumbnail_path=thumb_rel,
            tokens_used=tokens_used,
            api_cost=api_cost,
            completed=True,
        )
        task_service.set_progress(task_id, "completed", 100, "生成完成")
        task_service.clear_progress(task_id)

        return {
            "task_id": task_id,
            "status": "completed",
            "asset_id": asset_id,
            "result_path": saved.relative_path,
            "tokens_used": tokens_used,
        }

    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        logger.exception("Task %s failed", task_id)
        # 异步任务型 provider（如本地 CLI）：已提交的任务携带 submit_id，落库以便 retry 断点续查
        submit_id = getattr(e, "submit_id", None)
        if submit_id:
            _persist_submit_id(task_id, submit_id)
        _update_task(task_id, status="failed", error_msg=err_msg, completed=True)
        task_service.set_progress(task_id, "failed", 0, err_msg)
        # 失败时保留 Redis 进度一段时间，让 SSE 推送失败事件后由客户端断开
        # 但为避免无限残留，1 分钟后清理（这里立即清理由 SSE 端点已能从 DB 兜底）
        return {"task_id": task_id, "status": "failed", "error": err_msg}


def _load_provider_for_task_via_db(task_id: str):
    """从 DB 读取 task 并加载 Provider。"""
    with db_session() as db:
        task = db.get(Task, task_id)
        if not task:
            raise ProviderError(f"Task {task_id} not found")
        provider_slug = task.provider
        provider_row = (
            db.query(ApiProvider)
            .filter((ApiProvider.slug == provider_slug) | (ApiProvider.id == provider_slug))
            .first()
        )
        if provider_row:
            try:
                api_key = decrypt(provider_row.api_key_enc)
            except Exception:
                api_key = ""
            config = json.loads(provider_row.config_json or "{}")
            base_url = provider_row.base_url
            slug = provider_row.slug
        else:
            slug = provider_slug
            api_key = ""
            config = {}
            base_url = None

    return get_provider(slug, base_url=base_url, api_key=api_key, config=config), slug


def _filter_kwargs(func, kwargs: dict[str, Any]) -> dict[str, Any]:
    """过滤掉目标函数不接受的 kwargs（简化 Provider 间参数差异）。"""
    import inspect
    try:
        sig = inspect.signature(func)
        params = set(sig.parameters.keys())
        # 移除 self/cls 与通用 kwargs
        params.discard("self")
        params.discard("cls")
        accepted = {k: v for k, v in kwargs.items() if k in params}
        # 如果有 **kwargs，则全部透传
        for p in sig.parameters.values():
            if p.kind == inspect.Parameter.VAR_KEYWORD:
                return kwargs
        return accepted
    except Exception:
        return kwargs


@celery_app.task(name="app.worker.backup_database_task")
def backup_database_task() -> dict[str, Any]:
    """定时数据库备份。"""
    try:
        path = backup_database(keep_count=7)
        logger.info("Backup completed: %s", path)
        return {"success": True, "path": path}
    except Exception as e:
        logger.exception("Backup failed")
        return {"success": False, "error": str(e)}


# ============================================================
# 即梦 CLI 引导任务（必须在 worker 节点执行：生成任务在 worker 内调用 CLI）
# ============================================================

@celery_app.task(name="app.worker.dreamina_cli_status")
def dreamina_cli_status_task(cli_path: str | None = None) -> dict[str, Any]:
    """探测 worker 节点上即梦 CLI 的安装 / 登录状态。"""
    from .services import dreamina_cli_service
    return dreamina_cli_service.get_status(cli_path)


@celery_app.task(name="app.worker.dreamina_cli_install")
def dreamina_cli_install_task() -> dict[str, Any]:
    """在 worker 节点执行官方安装脚本（幂等，可重复触发作为升级）。"""
    from .services import dreamina_cli_service
    return dreamina_cli_service.install_cli()


@celery_app.task(name="app.worker.dreamina_cli_login_start")
def dreamina_cli_login_start_task(cli_path: str | None = None) -> dict[str, Any]:
    """启动 headless 登录，返回 verification_uri / user_code / device_code。"""
    from .services import dreamina_cli_service
    return dreamina_cli_service.start_login(cli_path)


@celery_app.task(name="app.worker.dreamina_cli_login_check")
def dreamina_cli_login_check_task(cli_path: str | None = None) -> dict[str, Any]:
    """校验 headless 登录是否已在浏览器完成。"""
    from .services import dreamina_cli_service
    return dreamina_cli_service.check_login(cli_path)


@celery_app.task(name="app.worker.dreamina_cli_user_credit")
def dreamina_cli_user_credit_task(cli_path: str | None = None) -> dict[str, Any]:
    """worker 侧连通性自检（供 Provider「测试连通」使用）。"""
    from .services import dreamina_cli_service
    return dreamina_cli_service.user_credit_check(cli_path)


_DREAMINA_AUTO_INSTALL_MAX_ATTEMPTS = 3


@worker_ready.connect
def _dreamina_cli_bootstrap(sender=None, **kwargs) -> None:  # noqa: ANN001
    """worker 就绪时提供即梦 CLI 引导：已装则提示登录，未装则自动安装。

    自动安装失败最多重试 3 次（Redis 计数），避免网络异常时无限循环。
    """
    try:
        from .services import dreamina_cli_service as dcs

        status = dcs.get_status()
        if status["installed"]:
            logger.info(
                "[即梦CLI] worker 节点已安装即梦 CLI（version=%s, logged_in=%s, path=%s）",
                status.get("version"), status.get("logged_in"), status.get("cli_path"),
            )
            if not status["logged_in"]:
                logger.info(
                    "[即梦CLI] 尚未登录：请打开 设置 → 服务管理 → 即梦 CLI，按引导完成 dreamina login"
                )
            return

        if status["installing"]:
            logger.info("[即梦CLI] 检测到安装正在进行中，跳过自动安装")
            return

        try:
            attempts = int(dcs._redis().incr(dcs._INSTALL_ATTEMPTS_KEY))
            dcs._redis().expire(dcs._INSTALL_ATTEMPTS_KEY, 3600)
        except Exception:
            attempts = 1

        if attempts > _DREAMINA_AUTO_INSTALL_MAX_ATTEMPTS:
            logger.warning(
                "[即梦CLI] worker 节点未检测到即梦 CLI，且自动安装已失败 %s 次。"
                "请在 设置 → 服务管理 → 即梦 CLI 中手动触发安装，或在 worker 所在机器执行 "
                "curl -fsSL %s | bash",
                attempts - 1, dcs.INSTALL_SCRIPT_URL,
            )
            return

        logger.info("[即梦CLI] worker 节点未检测到即梦 CLI，开始自动安装（第 %s 次）…", attempts)
        dreamina_cli_install_task.delay()
    except Exception:
        logger.exception("[即梦CLI] 启动引导检查失败（不影响 worker 正常工作）")
