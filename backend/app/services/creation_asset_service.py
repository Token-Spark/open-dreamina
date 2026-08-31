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

"""创作资产（素材库）同步服务：乐观锁版本链 + 三方合并 + 项目管理。

云端对象布局（manifest v2）：
    team-assets/{项目}/project.json                          项目元数据（名称/成员名册）
    team-assets/{项目}/{owner_id}/{asset_id}/manifest.json    最新版本指针（仅人工排查，协议不读）
    team-assets/{项目}/{owner_id}/{asset_id}/manifest.N.json  版本链（append-only，协议唯一依据）
    team-assets/{项目}/{owner_id}/{asset_id}/{image|audio}.{sha12}.*  媒体文件（内容寻址，不可变）

同步协议（可信团队，人人可写，绝不盲覆盖）：
- 推送（CAS 乐观锁）：云端 version 必须等于本地 base_version 才允许推 v+1；
  不一致说明云端有我没看过的更新 → 拒绝并提示先拉取。
- 拉取（三方合并）：本地未修改 → 快进覆盖；本地已修改且云端也更新 → 冲突，
  云端版导入为副本（保两份），绝不静默丢数据。
- 签名：manifest 以团队共享密钥（TEAM_SECRET 或七牛密钥）做 HMAC，防伪造署名；
  签名不符不拒收，但结果中标记「来源可疑」留痕。

一致性说明（关键）：版本链发现（云端最新版本号）必须走 rsf list API（强一致），
绝不走 CDN 公网域名读——CDN 有传播延迟与 404 负缓存，上传后立即读可能拿不到，
会破坏 CAS 判断。CDN 只用于下载不可变的具体版本对象（manifest.N.json），
且失败时短重试兜底。manifest.json 最新指针仅供人工排查，协议不读它。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import uuid
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Asset, CreationAsset, Setting
from ..utils.time_utils import now_iso
from ..providers import ProviderError
from . import qiniu_service
from .asset_service import create_asset_record, delete_asset_files, resolve_asset_path
from ..utils.file_utils import detect_mime_type, make_thumbnail, save_uploaded_file

# owner_id / owner_name 持久化于 settings 表
_OWNER_ID_KEY = "creation_asset_owner_id"
_OWNER_NAME_KEY = "creation_asset_owner_name"

# 集中化自动同步配置（同样持久化于 settings 表）
_AUTO_SYNC_ENABLED_KEY = "creation_asset_auto_sync_enabled"
_AUTO_SYNC_TAG_KEY = "creation_asset_auto_sync_tag"
_LAST_AUTO_SYNC_KEY = "creation_asset_last_auto_sync"

MANIFEST_VERSION = 2
_SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9_\-\u4e00-\u9fff]")
_VERSIONED_MANIFEST_RE = re.compile(r"^manifest\.(\d+)\.json$")


# ---------------- 身份 ----------------

def get_or_create_owner(db: Session) -> tuple[str, str]:
    """获取（或首次生成）本实例的同步身份：owner_id + 展示名。"""
    items = {
        s.key: s.value
        for s in db.query(Setting).filter(
            Setting.key.in_([_OWNER_ID_KEY, _OWNER_NAME_KEY])
        ).all()
    }
    owner_id = items.get(_OWNER_ID_KEY) or ""
    owner_name = items.get(_OWNER_NAME_KEY) or ""
    changed = False
    if not owner_id:
        owner_id = uuid.uuid4().hex[:12]
        db.add(Setting(key=_OWNER_ID_KEY, value=owner_id))
        changed = True
    if not owner_name:
        owner_name = f"用户-{owner_id[:4]}"
        db.add(Setting(key=_OWNER_NAME_KEY, value=owner_name))
        changed = True
    if changed:
        db.commit()
    return owner_id, owner_name


def update_owner_name(db: Session, owner_name: str) -> tuple[str, str]:
    """修改展示名（owner_id 保持不变，云端目录不受影响）。"""
    owner_id, _ = get_or_create_owner(db)
    row = db.query(Setting).filter(Setting.key == _OWNER_NAME_KEY).first()
    if row:
        row.value = owner_name
    else:
        db.add(Setting(key=_OWNER_NAME_KEY, value=owner_name))
    db.commit()
    return owner_id, owner_name


# ---------------- 集中化自动同步配置 ----------------

def get_auto_sync_config(db: Session) -> dict:
    """读取自动同步配置：enabled + tag + last_sync_at。"""
    items = {
        s.key: s.value
        for s in db.query(Setting).filter(
            Setting.key.in_([_AUTO_SYNC_ENABLED_KEY, _AUTO_SYNC_TAG_KEY, _LAST_AUTO_SYNC_KEY])
        ).all()
    }
    return {
        "enabled": items.get(_AUTO_SYNC_ENABLED_KEY, "false").lower() == "true",
        "tag": items.get(_AUTO_SYNC_TAG_KEY, ""),
        "last_sync_at": items.get(_LAST_AUTO_SYNC_KEY, ""),
    }


def set_auto_sync_config(db: Session, enabled: bool, tag: str) -> dict:
    """写入自动同步配置（幂等 upsert）。tag 为空时表示关闭自动同步。"""
    tag = tag.strip() if tag else ""
    # tag 非空时做 sanitize（存储 raw tag，使用时再 sanitize 为 key_tag）
    pairs = {
        _AUTO_SYNC_ENABLED_KEY: "true" if (enabled and tag) else "false",
        _AUTO_SYNC_TAG_KEY: tag,
    }
    for key, value in pairs.items():
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()
    return get_auto_sync_config(db)


def update_last_auto_sync(db: Session) -> None:
    """记录最近一次自动同步时间。"""
    now = _now_iso()
    row = db.query(Setting).filter(Setting.key == _LAST_AUTO_SYNC_KEY).first()
    if row:
        row.value = now
    else:
        db.add(Setting(key=_LAST_AUTO_SYNC_KEY, value=now))
    db.commit()


def auto_sync_cycle(db: Session, tag: str) -> dict:
    """集中化自动同步一个周期：先推送本地变更 → 再拉取远端更新。

    用于 Celery 定时任务和前端手动触发。返回 push/pull 各自的汇总结果。
    单条失败不阻断整体；冲突自动保两份（_pull_one 已有逻辑）。
    """
    results: dict[str, list[dict]] = {"pushed": [], "pulled": []}
    errors: list[str] = []

    # 推送本地变更（CAS 乐观锁，指纹未变则自动跳过）
    try:
        results["pushed"] = sync_assets_by_tag(db, tag)
    except ProviderError as e:
        errors.append(f"推送失败: {e}")
        db.rollback()

    # 拉取远端更新（三方合并，冲突保两份）
    try:
        results["pulled"] = pull_assets_by_tag(db, tag)
    except ProviderError as e:
        errors.append(f"拉取失败: {e}")
        db.rollback()

    update_last_auto_sync(db)

    return {
        "tag": tag,
        "pushed": results["pushed"],
        "pulled": results["pulled"],
        "errors": errors,
    }


def sanitize_tag(tag: str) -> str:
    """标签转安全 key 片段：去除路径分隔符等危险字符。"""
    cleaned = _SAFE_KEY_RE.sub("-", tag.strip())
    return cleaned.strip("-") or "default"


def _now_iso() -> str:
    return now_iso()


def _load_tags(ca: CreationAsset) -> list[str]:
    return json.loads(ca.tags_json or "[]")


# ---------------- 指纹与签名 ----------------

def _team_secret() -> str:
    """团队共享密钥：优先 TEAM_SECRET，未设置时复用七牛密钥（同团队天然共享）。"""
    return settings.team_secret or settings.qiniu_secret_key


def _sign(asset_id: str, version: int, fingerprint: str) -> str:
    secret = _team_secret()
    payload = f"{asset_id}:{version}:{fingerprint}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _verify_signature(manifest: dict) -> bool | None:
    """校验 manifest 签名：True=有效，False=不符（来源可疑），None=未签名（兼容旧数据）。"""
    signature = manifest.get("signature")
    if not signature:
        return None
    expected = _sign(
        manifest.get("asset_id", ""),
        manifest.get("version") or 0,
        manifest.get("fingerprint") or "",
    )
    return hmac.compare_digest(expected, str(signature))


def _fingerprint(
    name: str, category: str, description: str, tags: list[str],
    image_sha: str | None, audio_sha: str | None,
) -> str:
    """内容指纹：元数据 + 媒体哈希的 SHA256，用于判断「本地是否改过」。"""
    payload = json.dumps(
        {
            "name": name, "category": category, "description": description,
            "tags": sorted(tags), "image_sha": image_sha or "", "audio_sha": audio_sha or "",
        },
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha(path) -> str | None:
    """文件内容的 SHA256（文件缺失返回 None）。"""
    if not path or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _media_sha(db: Session, asset_id: str | None) -> str | None:
    """关联媒体 Asset 的文件哈希。"""
    if not asset_id:
        return None
    asset = db.get(Asset, asset_id)
    path = resolve_asset_path(asset) if asset else None
    return _file_sha(path)


def local_fingerprint(db: Session, ca: CreationAsset) -> str:
    """本地创作资产当前内容指纹。"""
    return _fingerprint(
        ca.name, ca.category, ca.description, _load_tags(ca),
        _media_sha(db, ca.image_asset_id), _media_sha(db, ca.audio_asset_id),
    )


# ---------------- 版本链发现（rsf list，强一致） ----------------

def _scan_cloud_versions(keys: list[str], key_tag: str) -> dict[tuple[str, str], int]:
    """从 list 结果聚合 (owner_id, asset_id) → 云端最大版本号。

    版本号只从 manifest.N.json 文件名解析（append-only，rsf list 强一致），
    不读 manifest.json 指针（CDN 读可能滞后）。
    """
    prefix = f"{qiniu_service.TEAM_SYNC_KEY_PREFIX}/{key_tag}/"
    versions: dict[tuple[str, str], int] = {}
    for key in keys:
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].split("/")
        if len(parts) != 3:
            continue
        owner_id, asset_id, filename = parts
        m = _VERSIONED_MANIFEST_RE.match(filename)
        if m:
            pair = (owner_id, asset_id)
            versions[pair] = max(versions.get(pair, 0), int(m.group(1)))
    return versions


def _download_manifest_with_retry(key: str, attempts: int = 3, delay: float = 1.0) -> dict:
    """下载 manifest（CDN 传播延迟兜底：失败短重试）。"""
    last_error: Exception | None = None
    for i in range(attempts):
        try:
            return json.loads(qiniu_service.download_team_object(key))
        except Exception as e:  # noqa: BLE001 重试后仍失败则上抛，由调用方汇总
            last_error = e
            if i < attempts - 1:
                time.sleep(delay)
    raise last_error  # type: ignore[misc]


# ---------------- 推送（CAS 乐观锁） ----------------

def sync_assets_by_tag(db: Session, tag: str) -> list[dict]:
    """将该标签（项目）下「全部本地资产」上传云端，返回逐条结果。

    可信团队模型：remote 资产也可编辑并推送回原作者目录（target_owner=ca.owner_id）。
    单条失败/冲突不阻断其余。
    """
    owner_id, owner_name = get_or_create_owner(db)
    wanted = tag.strip()
    targets = [ca for ca in db.query(CreationAsset).all() if wanted in _load_tags(ca)]
    if not targets:
        raise ProviderError(f"标签「{wanted}」下没有可同步的本地资产，请先为资产打上该标签")

    key_tag = sanitize_tag(wanted)
    # 一次 list 拿到全目录版本链（强一致，作为 CAS 依据）
    cloud_versions = _scan_cloud_versions(qiniu_service.list_team_keys(key_tag), key_tag)
    results: list[dict] = []
    for ca in targets:
        try:
            item = _push_one(db, key_tag, owner_id, owner_name, ca, cloud_versions)
            results.append(item)
        except Exception as e:  # noqa: BLE001 单条失败汇总上报，不阻断批量
            db.rollback()
            results.append(
                {"asset_id": ca.id, "name": ca.name, "status": "failed", "message": str(e)}
            )
    # 顺带更新项目成员名册（失败不影响同步结果）
    try:
        _touch_project_members(db, key_tag, owner_id, owner_name)
    except Exception:  # noqa: BLE001 名册是辅助信息，静默降级
        db.rollback()
    return results


def push_single_asset(db: Session, ca: CreationAsset, tag: str) -> dict:
    """推送单个资产到指定标签（项目）的云端目录。

    与 sync_assets_by_tag 的区别：仅推送这一条资产，不扫描整标签，
    不影响该标签下其他资产，适合创建/编辑后即刻推送。
    """
    owner_id, owner_name = get_or_create_owner(db)
    key_tag = sanitize_tag(tag.strip())
    cloud_versions = _scan_cloud_versions(qiniu_service.list_team_keys(key_tag), key_tag)
    item = _push_one(db, key_tag, owner_id, owner_name, ca, cloud_versions)
    # 更新项目成员名册（失败不影响推送结果）
    try:
        _touch_project_members(db, key_tag, owner_id, owner_name)
    except Exception:  # noqa: BLE001 名册是辅助信息，静默降级
        db.rollback()
    return item


def _push_one(
    db: Session, key_tag: str, owner_id: str, owner_name: str, ca: CreationAsset,
    cloud_versions: dict[tuple[str, str], int],
) -> dict:
    """推送单个资产：CAS 检查（list 版本链）→ 上传媒体 → 写 manifest.{v}。"""
    # 推送回资产原作者目录（remote 资产推回创建者处，保持版本链连续）
    target_owner = ca.owner_id or owner_id
    cloud_version = cloud_versions.get((target_owner, ca.id), 0)

    if ca.cloud_tag == key_tag:
        # 已在该目录建立版本链：云端版本必须与本地基线一致才允许推 v+1
        if cloud_version != ca.base_version:
            return {
                "asset_id": ca.id, "name": ca.name, "status": "conflict",
                "message": f"云端已有 v{cloud_version}（本地基于 v{ca.base_version}），请先拉取合并后再推送",
            }
        # 内容指纹未变 → 跳过（集中化自动同步的核心优化，避免无效写入）
        if ca.base_fingerprint and local_fingerprint(db, ca) == ca.base_fingerprint:
            return {"asset_id": ca.id, "name": ca.name, "status": "up_to_date",
                    "version": ca.base_version, "message": "内容未变更"}
        new_version = cloud_version + 1
    elif cloud_version > 0:
        # 同一资产 id 在目标目录已存在他人版本链，不确定来源，保守拒绝
        return {
            "asset_id": ca.id, "name": ca.name, "status": "conflict",
            "message": f"目录 {key_tag} 下已存在该资产的云端版本 v{cloud_version}，请先拉取确认",
        }
    else:
        # 该目录新链，版本从 1 开始
        new_version = 1

    # 上传媒体并计算哈希
    files: dict[str, dict] = {}
    for role, asset_id in (("image", ca.image_asset_id), ("audio", ca.audio_asset_id)):
        if not asset_id:
            continue
        asset = db.get(Asset, asset_id)
        path = resolve_asset_path(asset) if asset else None
        if not asset or not path:
            continue
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        ext = path.suffix.lower() or ".bin"
        # 修正旧数据中 application/octet-stream 的 mime_type（如被误判的 webp 图片）
        effective_mime = asset.mime_type or ""
        if not effective_mime or effective_mime == "application/octet-stream":
            effective_mime = detect_mime_type(path.name, data, effective_mime)
        # 内容寻址文件名：同一资产换图后 key 不同，对象不可变 → CDN 缓存天然安全
        filename = f"{role}.{sha[:12]}{ext}"
        qiniu_service.upload_team_object(
            qiniu_service.build_team_key(key_tag, target_owner, ca.id, filename), data
        )
        files[role] = {
            "filename": filename,
            "mime_type": effective_mime,
            "file_size": asset.file_size,
            "sha256": sha,
        }

    fingerprint = _fingerprint(
        ca.name, ca.category, ca.description, _load_tags(ca),
        files.get("image", {}).get("sha256"), files.get("audio", {}).get("sha256"),
    )
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "asset_id": ca.id,
        "name": ca.name,
        "category": ca.category,
        "description": ca.description,
        "tags": _load_tags(ca),
        "owner_id": target_owner,
        "owner_name": ca.owner_name or owner_name,
        "created_at": ca.created_at,
        "updated_at": ca.updated_at,
        "version": new_version,
        "fingerprint": fingerprint,
        "signature": _sign(ca.id, new_version, fingerprint),
        "files": files,
    }
    body = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    # 先写历史版本（append-only，协议只认它），再更新最新指针（仅供人工排查）
    qiniu_service.upload_team_object(
        qiniu_service.versioned_manifest_key(key_tag, target_owner, ca.id, new_version), body
    )
    qiniu_service.upload_team_object(
        qiniu_service.manifest_key(key_tag, target_owner, ca.id), body
    )

    ca.base_version = new_version
    ca.base_fingerprint = fingerprint
    ca.cloud_tag = key_tag
    ca.synced_at = _now_iso()
    db.commit()
    return {"asset_id": ca.id, "name": ca.name, "status": "synced", "version": new_version}


# ---------------- 拉取（三方合并） ----------------

def pull_assets_by_tag(db: Session, tag: str) -> list[dict]:
    """从云端拉取该标签（项目）下全部资产，按三方合并规则导入。

    - 本地无 → 导入；版本一致 → 已是最新；云端未动 → 跳过（本地待推送）；
    - 本地未改 → 快进更新；两边都改 → 冲突，云端版导入为副本（保两份）。
    """
    get_or_create_owner(db)
    key_tag = sanitize_tag(tag.strip())
    # rsf list 发现每个资产的最大版本号（强一致），再下载对应的 manifest.N.json
    versions = _scan_cloud_versions(qiniu_service.list_team_keys(key_tag), key_tag)

    results: list[dict] = []
    for (owner_id, asset_id), version in sorted(versions.items()):
        mk = qiniu_service.versioned_manifest_key(key_tag, owner_id, asset_id, version)
        try:
            manifest = _download_manifest_with_retry(mk)
            results.append(_pull_one(db, key_tag, manifest))
        except Exception as e:  # noqa: BLE001 单条失败汇总上报，不阻断批量
            db.rollback()
            results.append({"asset_id": asset_id, "name": asset_id, "status": "failed",
                            "message": str(e)})
    return results


def _pull_one(db: Session, key_tag: str, manifest: dict) -> dict:
    """单个 manifest 的三方合并决策。"""
    asset_id = manifest.get("asset_id") or ""
    name = manifest.get("name", "")
    if not asset_id:
        return {"asset_id": "unknown", "name": name, "status": "skipped",
                "message": "manifest 缺少 asset_id"}
    version = manifest.get("version") or 0
    fingerprint = manifest.get("fingerprint") or ""
    # 签名校验：不拒收，但留痕提示
    sig_ok = _verify_signature(manifest)
    warning = "；签名校验失败，来源可疑，请人工确认" if sig_ok is False else ""

    local = db.get(CreationAsset, asset_id)
    if local is None:
        _apply_manifest(db, key_tag, manifest)
        return {"asset_id": asset_id, "name": name, "status": "imported",
                "version": version, "message": warning or None}

    if version == local.base_version and fingerprint == local.base_fingerprint:
        return {"asset_id": asset_id, "name": name, "status": "up_to_date",
                "version": version, "message": "已是最新"}
    if version <= local.base_version:
        return {"asset_id": asset_id, "name": name, "status": "skipped",
                "message": "本地有未推送的修改，请先推送"}

    # 云端领先：本地未改 → 快进；本地已改 → 冲突保两份
    if local_fingerprint(db, local) == local.base_fingerprint:
        _apply_manifest(db, key_tag, manifest, ca=local)
        return {"asset_id": asset_id, "name": name, "status": "updated",
                "version": version, "message": warning or None}

    _apply_manifest(db, key_tag, manifest,
                    new_id=uuid.uuid4().hex, name_override=f"{local.name}（云端 v{version}）")
    return {"asset_id": asset_id, "name": name, "status": "conflict", "version": version,
            "message": f"本地与云端均有修改，云端 v{version} 已导入为副本，请人工合并{warning}"}


def _apply_manifest(
    db: Session, key_tag: str, manifest: dict,
    ca: CreationAsset | None = None, new_id: str | None = None,
    name_override: str | None = None,
) -> None:
    """将云端 manifest 落到本地：下载媒体（内容未变则复用）→ upsert CreationAsset。"""
    prefix_root = f"{qiniu_service.TEAM_SYNC_KEY_PREFIX}/{key_tag}"
    asset_id = new_id or manifest["asset_id"]
    owner_prefix = f"{prefix_root}/{manifest.get('owner_id', '')}/{manifest['asset_id']}"

    image_asset_id = None
    audio_asset_id = None
    old_image = ca.image_asset_id if ca else None
    old_audio = ca.audio_asset_id if ca else None
    for role, existing_id in (("image", old_image), ("audio", old_audio)):
        info = (manifest.get("files") or {}).get(role)
        if not info:
            continue
        # 媒体内容未变则复用本地文件，避免重复下载
        if existing_id and info.get("sha256") and _media_sha(db, existing_id) == info["sha256"]:
            if role == "image":
                image_asset_id = existing_id
            else:
                audio_asset_id = existing_id
            continue
        data = qiniu_service.download_team_object(f"{owner_prefix}/{info['filename']}")
        saved = save_uploaded_file(data, info["filename"])
        asset_type = "image" if role == "image" else "audio"
        thumb_rel = (
            make_thumbnail(saved.absolute_path, asset_type) if asset_type == "image" else None
        )
        record = create_asset_record(
            db=db, saved=saved, task_id=None, asset_type=asset_type,
            thumbnail_rel=thumb_rel, tags=[],
        )
        if role == "image":
            image_asset_id = record.id
        else:
            audio_asset_id = record.id

    version = manifest.get("version") or 0
    fingerprint = manifest.get("fingerprint") or ""
    if ca is None:
        ca = CreationAsset(
            id=asset_id,
            origin="remote",
            owner_id=manifest.get("owner_id", ""),
            owner_name=manifest.get("owner_name", ""),
        )
        db.add(ca)
    ca.name = name_override or manifest.get("name", "未命名")
    ca.category = manifest.get("category", "character")
    ca.description = manifest.get("description", "")
    ca.image_asset_id = image_asset_id
    ca.audio_asset_id = audio_asset_id
    ca.tags_json = json.dumps(manifest.get("tags", []), ensure_ascii=False)
    ca.base_version = version
    ca.base_fingerprint = fingerprint
    ca.cloud_tag = key_tag
    ca.synced_at = _now_iso()
    db.commit()

    # 清理被替换且不再被引用的旧媒体
    for old in (old_image, old_audio):
        if old and old not in (ca.image_asset_id, ca.audio_asset_id):
            cleanup_media_asset(db, old, exclude_ca_id=ca.id)


# ---------------- 项目（云端目录 + project.json） ----------------

def list_projects() -> list[dict]:
    """列举云端全部项目（扫描 team-assets/*\/project.json）。"""
    projects: list[dict] = []
    for key in qiniu_service.list_all_team_keys():
        parts = key.split("/")
        # team-assets/{tag}/project.json 恰好 3 段
        if len(parts) != 3 or parts[2] != "project.json":
            continue
        raw = qiniu_service.try_download_team_object(key)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        data.setdefault("tag", parts[1])
        projects.append(data)
    projects.sort(key=lambda p: p.get("created_at", ""))
    return projects


def create_project(db: Session, name: str, description: str) -> dict:
    """创建云端项目：project.json 写入 team-assets/{tag}/。"""
    owner_id, owner_name = get_or_create_owner(db)
    key_tag = sanitize_tag(name)
    # 存在性检查走 rsf list（强一致）；CDN 读可能滞后导致重复创建
    project_key = qiniu_service.project_key(key_tag)
    if project_key in qiniu_service.list_all_team_keys():
        raise ProviderError(f"项目「{name}」已存在（云端目录 {key_tag}），请换一个名称")
    project = {
        "name": name.strip(),
        "tag": key_tag,
        "description": description or "",
        "created_by": owner_name,
        "created_by_id": owner_id,
        "created_at": _now_iso(),
        "members": [{"owner_id": owner_id, "owner_name": owner_name}],
    }
    qiniu_service.upload_team_object(
        project_key, json.dumps(project, ensure_ascii=False).encode("utf-8")
    )
    return project


def _touch_project_members(db: Session, key_tag: str, owner_id: str, owner_name: str) -> None:
    """同步时顺带更新项目成员名册（不存在则补建，兼容旧标签目录）。"""
    project_key = qiniu_service.project_key(key_tag)
    raw = qiniu_service.try_download_team_object(project_key)
    project = json.loads(raw) if raw else {
        "name": key_tag, "tag": key_tag, "description": "",
        "created_by": owner_name, "created_by_id": owner_id,
        "created_at": _now_iso(), "members": [],
    }
    members: list[dict] = project.get("members") or []
    if not any(m.get("owner_id") == owner_id for m in members):
        members.append({"owner_id": owner_id, "owner_name": owner_name})
        project["members"] = members
        qiniu_service.upload_team_object(
            project_key, json.dumps(project, ensure_ascii=False).encode("utf-8")
        )


# ---------------- 媒体引用维护 ----------------

def is_asset_referenced(db: Session, asset_id: str, exclude_ca_id: str | None = None) -> bool:
    """媒体 Asset 是否仍被某个创作资产引用（删除前判断，避免误删共享文件）。"""
    q = db.query(CreationAsset).filter(
        (CreationAsset.image_asset_id == asset_id)
        | (CreationAsset.audio_asset_id == asset_id)
    )
    if exclude_ca_id:
        q = q.filter(CreationAsset.id != exclude_ca_id)
    return db.query(q.exists()).scalar()


def cleanup_media_asset(db: Session, asset_id: str | None, exclude_ca_id: str | None = None) -> None:
    """媒体 Asset 不再被引用时删除其记录与文件。"""
    if not asset_id or is_asset_referenced(db, asset_id, exclude_ca_id):
        return
    asset = db.get(Asset, asset_id)
    if asset:
        delete_asset_files(asset)
        db.delete(asset)
        db.commit()
