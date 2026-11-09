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

"""两种审阅模式共享的底层能力：路径安全、缩略图、媒体探测、目录列举。

制片人审阅（reviews）与镜头审片（shot-reviews）是两套独立的表与端点，
但「外部素材能否被访问」「缩略图怎么生成和存放」「可选目录怎么列」完全
相同。这里放唯一一份实现，两个 service 都从这里导入，避免镜头审片反向
依赖制片人审阅的私有函数、也避免安全校验出现两份不一致的实现。
"""
from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

from PIL import Image

from ..config import settings
from ..utils.file_utils import THUMBNAIL_WIDTH

# 缩略图存放根目录（与 assets 目录同级）
_THUMB_DIR_NAME = "review_thumbs"


def thumb_base_path() -> Path:
    """缩略图根目录：与 assets 目录同级的 review_thumbs/。

    审阅缩略图属于本实例生成的数据（非外部素材），统一落在数据根目录下，
    便于备份与清理；不依赖数据库文件位置。
    """
    p = settings.assets_path.parent / _THUMB_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def guess_asset_type(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "image"


def probe_media_meta(abs_path: Path, mime_type: str) -> tuple[int | None, int | None, float | None]:
    """探测图片宽高 / 视频宽高+时长。"""
    width = height = None
    duration: float | None = None
    asset_type = guess_asset_type(mime_type)
    if asset_type == "image":
        try:
            with Image.open(abs_path) as img:
                width, height = img.size
        except Exception:
            pass
    elif asset_type == "video":
        try:
            from ..utils.file_utils import _probe_video_meta
            width, height, duration = _probe_video_meta(abs_path)
        except Exception:
            pass
    return width, height, duration


def generate_review_thumbnail(
    abs_path: Path, session_id: str, mime_type: str
) -> str | None:
    """为审阅文件生成缩略图，返回相对 thumb_base_path 的路径。

    与资产缩略图不同：外部素材目录可能只读、且不应被写入，
    因此缩略图一律生成到 data/review_thumbs/{session_id}/ 下。
    """
    asset_type = guess_asset_type(mime_type)
    if asset_type == "audio":
        return None  # 音频无缩略图
    try:
        dest_dir = thumb_base_path() / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{uuid.uuid4().hex}_thumb.webp"

        if asset_type == "video":
            if not write_video_thumbnail(abs_path, dest):
                return None
        else:
            with Image.open(abs_path) as img:
                save_webp_thumbnail(img, dest)

        return str(dest.relative_to(thumb_base_path())).replace("\\", "/")
    except Exception:
        return None


def save_webp_thumbnail(img: "Image.Image", dest: Path) -> None:
    """等比缩放并保存为 WebP 缩略图。"""
    img = img.convert("RGB")
    if img.width <= 0:
        raise ValueError("图片宽度为 0")
    ratio = THUMBNAIL_WIDTH / img.width
    new_size = (THUMBNAIL_WIDTH, max(1, int(img.height * ratio)))
    img.resize(new_size, Image.LANCZOS).save(dest, format="WEBP", quality=85)


def write_video_thumbnail(source_abs: Path, dest: Path) -> bool:
    """用 ffmpeg 抽第一帧生成 WebP 缩略图。

    抽帧产物写入系统临时目录，避免污染外部素材目录（可能是只读挂载）。
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            frame_path = Path(tmp) / "frame.png"
            cmd = [
                "ffmpeg", "-y", "-i", str(source_abs),
                "-frames:v", "1", "-q:v", "2",
                str(frame_path),
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0 or not frame_path.exists():
                return False
            with Image.open(frame_path) as img:
                save_webp_thumbnail(img, dest)
        return True
    except Exception:
        return False


def resolve_thumbnail_path(thumb_rel: str | None) -> Path | None:
    """将 review_thumbs 下的相对路径解析为绝对路径。"""
    if not thumb_rel:
        return None
    p = thumb_base_path() / thumb_rel
    return p if p.exists() else None


def delete_thumbnail_file(thumb_rel: str | None) -> None:
    """删除缩略图文件（若存在）。失败静默忽略，不阻断扫描。"""
    if not thumb_rel:
        return
    try:
        p = thumb_base_path() / thumb_rel
        if p.is_file():
            p.unlink()
    except OSError:
        pass


# ---------------- 路径安全验证 ----------------

def is_within(path: Path, root: Path) -> bool:
    """判断 path 是否等于 root 或位于 root 之下。"""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_path_allowed(
    folder_path: str,
    roots: list[Path] | None = None,
    env_hint: str = "REVIEW_SOURCE_ROOTS",
) -> Path:
    """验证文件夹路径是否在配置允许的根目录下，返回解析后的绝对路径。

    安全要求：防止路径遍历攻击，只允许访问配置的根目录下的子目录。
    resolve() 会展开符号链接，因此指向外部的软链接同样会被拒绝。
    roots 缺省时使用制片人审阅的允许根目录；镜头审片传入自己的可写根目录。
    """
    requested = Path(folder_path).expanduser().resolve()
    for root in (roots if roots is not None else settings.review_source_paths):
        if not is_within(requested, root):
            continue
        if not requested.is_dir():
            raise ValueError(f"路径不是目录或不存在: {requested}")
        return requested
    raise ValueError(
        f"路径不在允许的审阅目录内: {folder_path}。"
        f"请在 .env 中配置 {env_hint} 指向素材所在目录。"
    )


def is_shot_path_allowed(folder_path: str) -> Path:
    """镜头审片专用的路径校验：使用可写根目录（SHOT_REVIEW_SOURCE_ROOTS）。"""
    return is_path_allowed(
        folder_path, settings.shot_review_source_paths, "SHOT_REVIEW_SOURCE_ROOTS"
    )


def list_review_folders(roots: list[Path] | None = None) -> list[dict]:
    """列出允许根目录及其下的子文件夹（递归两层），供前端选择审阅目标。

    返回格式：[{path, name, subdirs: [{path, name, subdirs: [{path, name}]}]}]
    roots 缺省时使用制片人审阅的允许根目录；镜头审片传入自己的可写根目录。
    """
    result: list[dict] = []
    for root in (roots if roots is not None else settings.review_source_paths):
        if not root.exists():
            result.append({"path": str(root), "name": root.name, "subdirs": [], "exists": False})
            continue
        subdirs: list[dict] = []
        try:
            for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                level2: list[dict] = []
                try:
                    for grandchild in sorted(child.iterdir(), key=lambda p: p.name.lower()):
                        if grandchild.is_dir() and not grandchild.name.startswith("."):
                            level2.append({"path": str(grandchild), "name": grandchild.name})
                except PermissionError:
                    pass
                subdirs.append({"path": str(child), "name": child.name, "subdirs": level2})
        except PermissionError:
            pass
        result.append({
            "path": str(root),
            "name": root.name,
            "subdirs": subdirs,
            "exists": True,
        })
    return result
