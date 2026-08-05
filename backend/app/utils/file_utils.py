"""文件存储与缩略图生成工具。

- 按规格 7.1 目录结构存储：images/videos/uploads 下按 YYYY-MM 子目录。
- 缩略图统一 WebP，宽度 400px（图片用 Pillow；视频缩略图调用 ffmpeg 抽帧）。
- DB 中只存相对路径（相对 ASSETS_DIR）。
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from ..config import settings

THUMBNAIL_WIDTH = 400

# MIME 扩展名映射（生成结果保存时使用）
EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}

MIME_BY_EXT = {v: k for k, v in EXT_BY_MIME.items()}


@dataclass
class SavedFile:
    relative_path: str
    absolute_path: Path
    file_size: int
    mime_type: str
    width: int | None
    height: int | None
    duration: float | None


def _month_folder() -> str:
    return datetime.now().strftime("%Y-%m")


def _subdir_for_type(asset_type: str) -> str:
    """asset_type=image -> images, video -> videos, 否则 uploads。"""
    mapping = {"image": "images", "video": "videos", "audio": "audio"}
    return mapping.get(asset_type, "uploads")


def _guess_asset_type(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "image"


def save_generated_file(
    file_bytes: bytes,
    mime_type: str,
    asset_type: str | None = None,
) -> SavedFile:
    """保存生成结果文件，返回相对/绝对路径及基本元信息（不含缩略图）。"""
    if asset_type is None:
        asset_type = _guess_asset_type(mime_type)

    subdir = _subdir_for_type(asset_type)
    month = _month_folder()
    ext = EXT_BY_MIME.get(mime_type, ".bin")
    filename = f"{uuid.uuid4().hex}{ext}"

    rel_dir = Path(subdir) / month
    abs_dir = settings.assets_path / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    abs_path = abs_dir / filename
    abs_path.write_bytes(file_bytes)

    width = height = None
    duration = None
    if asset_type == "image":
        try:
            with Image.open(abs_path) as img:
                width, height = img.size
        except Exception:
            pass
    elif asset_type == "video":
        width, height, duration = _probe_video_meta(abs_path)

    rel_path = f"{rel_dir.as_posix()}/{filename}"
    return SavedFile(
        relative_path=rel_path,
        absolute_path=abs_path,
        file_size=len(file_bytes),
        mime_type=mime_type,
        width=width,
        height=height,
        duration=duration,
    )


def save_uploaded_file(file_bytes: bytes, filename: str) -> SavedFile:
    """保存用户上传的参考图（图生图/图生视频输入）。"""
    ext = Path(filename).suffix.lower() or ".bin"
    mime_type = MIME_BY_EXT.get(ext, "application/octet-stream")

    month = _month_folder()
    new_name = f"{uuid.uuid4().hex}{ext}"
    rel_dir = Path("uploads") / month
    abs_dir = settings.assets_path / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / new_name
    abs_path.write_bytes(file_bytes)

    width = height = None
    if mime_type.startswith("image/"):
        try:
            with Image.open(abs_path) as img:
                width, height = img.size
        except Exception:
            pass

    rel_path = f"{rel_dir.as_posix()}/{new_name}"
    return SavedFile(
        relative_path=rel_path,
        absolute_path=abs_path,
        file_size=len(file_bytes),
        mime_type=mime_type,
        width=width,
        height=height,
        duration=None,
    )


def make_thumbnail(source_abs: Path, asset_type: str) -> str | None:
    """生成缩略图（WebP, 400px 宽），返回相对 ASSETS_DIR 的路径。

    失败时返回 None（不阻断主流程）。
    """
    try:
        if asset_type == "video":
            return _make_video_thumbnail(source_abs)
        return _make_image_thumbnail(source_abs)
    except Exception:
        return None


def _make_image_thumbnail(source_abs: Path) -> str | None:
    with Image.open(source_abs) as img:
        img = img.convert("RGB")
        ratio = THUMBNAIL_WIDTH / img.width
        new_height = max(1, int(img.height * ratio))
        thumb = img.resize((THUMBNAIL_WIDTH, new_height), Image.LANCZOS)

        thumb_name = f"{source_abs.stem}_thumb.webp"
        thumb_path = source_abs.parent / thumb_name
        thumb.save(thumb_path, format="WEBP", quality=85)
        return _to_relative(thumb_path)


def _make_video_thumbnail(source_abs: Path) -> str | None:
    """用 ffmpeg 抽第一帧后生成 WebP 缩略图。"""
    frame_path = source_abs.parent / f"{source_abs.stem}_frame.png"
    cmd = [
        "ffmpeg", "-y", "-i", str(source_abs),
        "-frames:v", "1", "-q:v", "2",
        str(frame_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0 or not frame_path.exists():
        return None
    try:
        rel = _make_image_thumbnail(frame_path)
    finally:
        try:
            frame_path.unlink(missing_ok=True)
        except Exception:
            pass
    return rel


def _probe_video_meta(abs_path: Path) -> tuple[int | None, int | None, float | None]:
    """使用 ffprobe 读取视频宽高/时长。失败返回 None 元组。"""
    width = height = duration = None
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "default=noprint_wrappers=1",
            str(abs_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=15, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("width="):
                    width = int(line.split("=", 1)[1])
                elif line.startswith("height="):
                    height = int(line.split("=", 1)[1])
                elif line.startswith("duration="):
                    duration = float(line.split("=", 1)[1])
    except Exception:
        pass
    return width, height, duration


def _to_relative(abs_path: Path) -> str:
    try:
        return abs_path.relative_to(settings.assets_path).as_posix()
    except ValueError:
        return abs_path.as_posix()


def resolve_relative(relative_path: str) -> Path:
    """将 DB 中的相对路径解析为绝对路径。"""
    return settings.assets_path / relative_path


def delete_relative(relative_path: str | None) -> None:
    """删除相对路径对应的文件（若存在）。"""
    if not relative_path:
        return
    try:
        p = resolve_relative(relative_path)
        if p.exists() and p.is_file():
            p.unlink()
    except Exception:
        pass


def render_placeholder_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    bg_color: tuple[int, int, int] = (30, 30, 36),
    fg_color: tuple[int, int, int] = (245, 245, 247),
) -> bytes:
    """用 Pillow 绘制一张带 prompt 文字的占位图（Mock Provider 使用）。"""
    img = Image.new("RGB", (width, height), bg_color)
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(img)

    title = "Open Dreamina · Mock"
    try:
        font_large = ImageFont.truetype("arial.ttf", size=48)
        font_small = ImageFont.truetype("arial.ttf", size=28)
    except OSError:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # 标题居中
    tb = draw.textbbox((0, 0), title, font=font_large)
    draw.text(
        ((width - (tb[2] - tb[0])) // 2, 60),
        title,
        font=font_large,
        fill=(255, 255, 255),
    )

    # prompt 文字换行
    max_chars = max(10, width // 18)
    lines: list[str] = []
    for raw_line in (prompt or "").splitlines() or ["(empty prompt)"]:
        chunk = ""
        for ch in raw_line:
            chunk += ch
            if len(chunk) >= max_chars:
                lines.append(chunk)
                chunk = ""
        lines.append(chunk)
    if not lines:
        lines = ["(empty prompt)"]

    y = height // 2 - len(lines) * 18
    for line in lines[:24]:
        draw.text((60, y), line, font=font_small, fill=fg_color)
        y += 36

    # 尺寸标注
    size_text = f"{width} x {height}"
    draw.text((60, height - 60), size_text, font=font_small, fill=(160, 160, 168))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
