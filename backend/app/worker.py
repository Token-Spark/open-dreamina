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
from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

from .config import settings
from .database import db_session
from .models import ApiProvider, Asset, Task
from .providers import ProviderError, get_provider
from .providers.sparkhub_base import SparkHubBaseProvider
from .services import task_service
from .services.asset_audit_service import asset_public_url
from .services.asset_service import (
    create_asset_record,
    delete_asset_files,
    generate_thumbnail_for,
)
from .services.backup_service import backup_database
from .utils.crypto import decrypt
from .utils.file_utils import _guess_asset_type, resolve_relative, save_uploaded_file
from .utils.time_utils import now_iso as _now

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
        # 定期清理 worker 中断后遗留的 running 孤儿任务，避免任务永久卡在"生成中"
        "recover-stale-tasks": {
            "task": "app.worker.recover_stale_tasks",
            "schedule": crontab(minute="*/5"),
        },
        # 集中化自动同步：每 2 分钟推送本地变更 + 拉取远端更新，
        # 保证团队成员即时获取最新素材（仅在 auto-sync 开启且七牛云已配置时生效）
        "auto-sync-creation-assets": {
            "task": "app.worker.auto_sync_creation_assets_task",
            "schedule": crontab(minute="*/2"),
        },
    },
)


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


# 上游状态 → 本地进度/文案映射（Spark Hub query_task 的 data.status）。
# 上游不提供百分比进度，这里把状态迁移映射为进度台阶，避免前端进度条长时间不动被误判为卡死。
_SPARKHUB_STATUS_PROGRESS: dict[str, tuple[int, str]] = {
    "queued": (40, "上游排队中…"),
    "running": (55, "上游生成中…"),
}


def _on_sparkhub_status(task_id: str, status: str, elapsed_s: float) -> None:
    """Spark Hub 状态变更回调：把上游进度台阶推送到 Redis/DB，供 SSE 与轮询读取。

    status/elapsed 由 provider 的 _poll 在状态首次变化时回调（同步、异常已由 provider 兜底）。
    """
    mapping = _SPARKHUB_STATUS_PROGRESS.get(status)
    if mapping is None:
        return
    pct, base_msg = mapping
    # 只推状态文案，已等待时长由前端基于 createdAt 本地实时计时（避免后端回调冻结）
    task_service.set_progress(task_id, "running", pct, base_msg)
    _update_task(task_id, progress=pct)


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


def _build_sparkhub_seedance_ref_kwargs(
    db, raw_ids: list[str], frame_mode: str | None
) -> dict[str, Any]:
    """为 Spark Hub Seedance 图生视频构造参考素材 URL kwargs（审核后 asset:// 地址）。

    按素材类型分别路由到上游 API 对应字段：
    - 图片：first/first_last → first_image_url/last_image_url；reference/text → image_urls
    - 视频：video_urls（使用审核后的 asset:// 地址）
    - 音频：audio_urls（需公网 URL；暂未接入，跳过）

    图片/视频参考素材需先通过 seedance_asset_audit 审核，未审核或审核未通过的直接报错，
    避免上游拒绝。
    """
    assets = [db.get(Asset, aid) for aid in raw_ids]
    assets = [a for a in assets if a is not None]
    if not assets:
        return {}
    # 校验：图片/视频必须审核通过（音频无需审核，跳过校验）
    for a in assets:
        if a.type == "audio":
            continue
        if a.audit_status != "active" or not a.audit_asset_url:
            raise ProviderError(
                f"参考素材 {a.id} 尚未通过审核（status={a.audit_status or 'none'}），"
                "请等待审核通过后再生成"
            )

    kwargs_out: dict[str, Any] = {}
    # 按素材类型分流：视频 → video_urls，图片按帧模式分发
    image_urls = [
        a.audit_asset_url for a in assets
        if a.type not in ("video", "audio") and a.audit_asset_url
    ]
    video_urls = [
        a.audit_asset_url for a in assets
        if a.type == "video" and a.audit_asset_url
    ]

    if video_urls:
        kwargs_out["video_urls"] = video_urls

    if image_urls:
        if frame_mode == "first_last":
            if len(image_urls) < 2:
                raise ProviderError("首尾帧模式需要 2 张参考图（首帧 + 尾帧），当前不足")
            kwargs_out["first_image_url"] = image_urls[0]
            kwargs_out["last_image_url"] = image_urls[1]
        elif frame_mode == "first":
            kwargs_out["first_image_url"] = image_urls[0]
        else:
            # reference / text / auto / 默认：多模态参考图
            kwargs_out["image_urls"] = image_urls

    return kwargs_out


async def _build_sparkhub_seedream_ref_kwargs(db, raw_ids: list[str]) -> dict[str, Any]:
    assets = [db.get(Asset, aid) for aid in raw_ids]
    assets = [a for a in assets if a is not None]
    if not assets:
        return {}
    invalid = [a.id for a in assets if a.type != "image"]
    if invalid:
        raise ProviderError(f"Seedream 图生图仅支持图片参考素材：{', '.join(invalid)}")
    urls = [await asset_public_url(asset) for asset in assets]
    return {"image_urls": urls}


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

        # Spark Hub 异步任务：把上游状态迁移回调注入 provider，实时推送进度台阶给前端
        if isinstance(provider, SparkHubBaseProvider):
            provider.on_status = lambda s, e: _on_sparkhub_status(task_id, s, e)

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
        for k in ("negative_prompt", "width", "height", "steps", "guidance_scale", "seed", "duration", "strength", "resolution", "count"):
            if k in params:
                kwargs[k] = params[k]
        # 断点续查：上一轮失败后落库的 submit_id 透传给 provider，避免重新 submit 重复扣费
        if params.get("submit_id"):
            kwargs["submit_id"] = params["submit_id"]
        # Seedance 图生视频模式：first | first_last | reference
        if params.get("frame_mode"):
            kwargs["frame_mode"] = params["frame_mode"]

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
                if slug == "sparkhub-seedream":
                    with db_session() as db:
                        ref_kwargs = loop.run_until_complete(
                            _build_sparkhub_seedream_ref_kwargs(db, raw_ids)
                        )
                    kwargs.update(ref_kwargs)
                result = loop.run_until_complete(provider.image_to_image(image_bytes=image_bytes_list, prompt=prompt, **_filter_kwargs(provider.image_to_image, kwargs)))
            elif task_type == "text2video":
                result = loop.run_until_complete(provider.text_to_video(prompt=prompt, **_filter_kwargs(provider.text_to_video, kwargs)))
            elif task_type == "img2video":
                if slug == "sparkhub-seedance":
                    # Spark Hub Seedance：参考素材需先审核，使用审核后的 asset:// 地址
                    # 作为 first_image_url / last_image_url / image_urls，而非本地字节。
                    with db_session() as db:
                        ref_kwargs = _build_sparkhub_seedance_ref_kwargs(
                            db, raw_ids, kwargs.get("frame_mode")
                        )
                    kwargs.update(ref_kwargs)
                    result = loop.run_until_complete(
                        provider.image_to_video(
                            image_bytes=b"",
                            prompt=prompt,
                            **_filter_kwargs(provider.image_to_video, kwargs),
                        )
                    )
                else:
                    first_bytes = image_bytes_list[0] if image_bytes_list else None
                    if first_bytes is None:
                        raise ProviderError("图生视频缺少输入图片")
                    if kwargs.get("frame_mode") == "first_last":
                        if len(image_bytes_list) < 2:
                            raise ProviderError(
                                "首尾帧模式需要 2 张参考图（首帧 + 尾帧），当前不足"
                            )
                        kwargs["last_image_bytes"] = image_bytes_list[1]
                    elif kwargs.get("frame_mode") == "reference":
                        kwargs["reference_image_bytes_list"] = image_bytes_list
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

        # 保存文件（支持多图：Provider 返回多张时逐张落盘并各建一条资产记录）
        from .utils.file_utils import save_generated_file
        files = result.files or [(result.file_bytes, result.mime_type)]
        asset_ids: list[str] = []
        first_saved = None
        first_thumb_rel = None
        for file_bytes, mime_type in files:
            saved = save_generated_file(file_bytes, mime_type)

            # 用修正后的 mime_type（save_generated_file 内部已做 magic-bytes 嗅探）
            # 推导 asset_type，避免上游 octet-stream 导致 webp 被误判为 video
            asset_type = _guess_asset_type(saved.mime_type)
            thumb_rel = generate_thumbnail_for(saved, asset_type)
            if first_saved is None:
                first_saved = saved
                first_thumb_rel = thumb_rel

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
                asset_ids.append(asset.id)

        # 把有序结果资产 ID 合并进 params 落库，供任务详情/SSE 派生 result_urls（不覆盖其它参数）
        with db_session() as db:
            task = db.get(Task, task_id)
            if task:
                task_params: dict[str, Any] = json.loads(task.params_json or "{}")
                task_params["result_asset_ids"] = asset_ids
                task.params_json = json.dumps(task_params, ensure_ascii=False)

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
            result_path=first_saved.relative_path,
            thumbnail_path=first_thumb_rel,
            tokens_used=tokens_used,
            api_cost=api_cost,
            completed=True,
        )
        task_service.set_progress(task_id, "completed", 100, "生成完成")
        task_service.clear_progress(task_id)

        return {
            "task_id": task_id,
            "status": "completed",
            "asset_ids": asset_ids,
            "result_path": first_saved.relative_path,
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


@celery_app.task(name="app.worker.recover_stale_tasks")
def recover_stale_tasks() -> dict[str, Any]:
    """清理 worker 中断后遗留的 running 孤儿任务（标记为 failed）。

    由 celery-beat 每 5 分钟触发一次；worker 启动时也会立即执行一次，
    确保重启后能马上恢复上次中断遗留的任务。
    """
    try:
        count = task_service.recover_stale_tasks()
        if count:
            logger.info("Recovered %s stale task(s) stuck in running", count)
        return {"recovered": count}
    except Exception:
        logger.exception("recover_stale_tasks failed")
        return {"recovered": 0, "error": "recovery failed"}


@celery_app.task(name="app.worker.auto_sync_creation_assets_task")
def auto_sync_creation_assets_task() -> dict[str, Any]:
    """集中化自动同步定时任务：推送本地变更 + 拉取远端更新。

    读取 settings 表中的 auto-sync 配置；未启用 / 未配置 tag / 七牛云未配置时静默跳过。
    """
    from .services import creation_asset_service as svc, qiniu_service

    # 前置检查：七牛云未配置 → 跳过
    if not qiniu_service.is_configured():
        return {"skipped": True, "reason": "qiniu_not_configured"}

    try:
        with db_session() as db:
            config = svc.get_auto_sync_config(db)
        if not config["enabled"] or not config["tag"]:
            return {"skipped": True, "reason": "auto_sync_disabled"}

        tag = config["tag"]
        with db_session() as db:
            result = svc.auto_sync_cycle(db, tag)

        pushed_count = sum(
            1 for r in result["pushed"] if r.get("status") == "synced"
        )
        pulled_count = sum(
            1 for r in result["pulled"]
            if r.get("status") in ("imported", "updated")
        )
        if pushed_count or pulled_count or result["errors"]:
            logger.info(
                "[自动同步] tag=%s: 推送 %d 条, 拉取 %d 条%s",
                tag, pushed_count, pulled_count,
                f", 错误 {len(result['errors'])} 条" if result["errors"] else "",
            )
        return {
            "tag": tag,
            "pushed": pushed_count,
            "pulled": pulled_count,
            "errors": result["errors"],
        }
    except Exception:
        logger.exception("[自动同步] 执行失败")
        return {"error": "auto_sync_failed"}


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
    # 先恢复上次中断遗留的 running 孤儿任务，避免重启后任务仍卡在"生成中"
    try:
        recovered = task_service.recover_stale_tasks()
        if recovered:
            logger.info("[恢复] worker 启动时恢复 %s 个卡在 running 的孤儿任务", recovered)
    except Exception:
        logger.exception("[恢复] worker 启动时恢复孤儿任务失败（不影响 worker 正常工作）")

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
