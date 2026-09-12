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

"""比例 × 分辨率 → 实际宽高，以及模型能力查询。

口径与前端 `frontend/src/lib/generation.ts` 的 IMAGE_SIZE_TABLE / VIDEO_SIZE_TABLE /
VIDEO_MODEL_SPECS / imageResolutionsForModel 保持一致：智能体只传「比例 + 分辨率」，
由本模块换算成后端真正使用的 width/height，避免各处硬编码像素值。
前端表格调整时需同步本文件。
"""
from __future__ import annotations

from typing import Any

# ---------------- 可选值 ----------------

IMAGE_ASPECT_RATIOS = ["auto", "21:9", "16:9", "3:2", "4:3", "1:1", "3:4", "2:3", "9:16"]
VIDEO_ASPECT_RATIOS = ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]
IMAGE_RESOLUTIONS = ["1K", "2K", "3K", "4K"]
VIDEO_RESOLUTIONS = ["480p", "720p", "1080p", "2160p"]

DEFAULT_ASPECT_RATIO = {"image": "1:1", "video": "16:9"}
DEFAULT_RESOLUTION = {"image": "2K", "video": "720p"}

# auto 比例 / 未知档位的回退尺寸
DEFAULT_SIZE: dict[str, dict[str, int]] = {
    "image": {"width": 1024, "height": 1024},
    "video": {"width": 1280, "height": 720},
}

# ---------------- 像素表 ----------------

IMAGE_SIZE_TABLE: dict[str, dict[str, dict[str, int]]] = {
    "1K": {
        "1:1": {"width": 1024, "height": 1024},
        "3:4": {"width": 768, "height": 1024},
        "4:3": {"width": 1024, "height": 768},
        "16:9": {"width": 1024, "height": 576},
        "9:16": {"width": 576, "height": 1024},
        "3:2": {"width": 1024, "height": 640},
        "2:3": {"width": 640, "height": 1024},
        "21:9": {"width": 1024, "height": 448},
    },
    "2K": {
        "1:1": {"width": 2048, "height": 2048},
        "3:4": {"width": 1728, "height": 2304},
        "4:3": {"width": 2304, "height": 1728},
        "16:9": {"width": 2848, "height": 1600},
        "9:16": {"width": 1600, "height": 2848},
        "3:2": {"width": 2496, "height": 1664},
        "2:3": {"width": 1664, "height": 2496},
        "21:9": {"width": 3136, "height": 1344},
    },
    "3K": {
        "1:1": {"width": 3072, "height": 3072},
        "3:4": {"width": 2592, "height": 3456},
        "4:3": {"width": 3456, "height": 2592},
        "16:9": {"width": 4272, "height": 2400},
        "9:16": {"width": 2400, "height": 4272},
        "3:2": {"width": 3744, "height": 2496},
        "2:3": {"width": 2496, "height": 3744},
        "21:9": {"width": 4704, "height": 2016},
    },
    "4K": {
        "1:1": {"width": 4096, "height": 4096},
        "3:4": {"width": 3456, "height": 4608},
        "4:3": {"width": 4608, "height": 3456},
        "16:9": {"width": 5696, "height": 3200},
        "9:16": {"width": 3200, "height": 5696},
        "3:2": {"width": 4992, "height": 3328},
        "2:3": {"width": 3328, "height": 4992},
        "21:9": {"width": 6272, "height": 2688},
    },
}

VIDEO_SIZE_TABLE: dict[str, dict[str, dict[str, int]]] = {
    "480p": {
        "16:9": {"width": 864, "height": 480},
        "4:3": {"width": 736, "height": 544},
        "1:1": {"width": 640, "height": 640},
        "3:4": {"width": 544, "height": 736},
        "9:16": {"width": 480, "height": 864},
        "21:9": {"width": 960, "height": 416},
    },
    "720p": {
        "16:9": {"width": 1248, "height": 704},
        "4:3": {"width": 1120, "height": 832},
        "1:1": {"width": 960, "height": 960},
        "3:4": {"width": 832, "height": 1120},
        "9:16": {"width": 704, "height": 1248},
        "21:9": {"width": 1504, "height": 640},
    },
    "1080p": {
        "16:9": {"width": 1920, "height": 1088},
        "4:3": {"width": 1664, "height": 1248},
        "1:1": {"width": 1440, "height": 1440},
        "3:4": {"width": 1248, "height": 1664},
        "9:16": {"width": 1088, "height": 1920},
        "21:9": {"width": 2176, "height": 928},
    },
    "2160p": {
        "16:9": {"width": 3840, "height": 2176},
        "4:3": {"width": 3328, "height": 2496},
        "1:1": {"width": 2880, "height": 2880},
        "3:4": {"width": 2496, "height": 3328},
        "9:16": {"width": 2176, "height": 3840},
        "21:9": {"width": 4352, "height": 1856},
    },
}


def resolve_size(
    mode: str,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
) -> dict[str, Any]:
    """把「内容模式 + 比例 + 分辨率」换算为 width/height。

    模式为 image / video；比例或分辨率缺省时使用该模式默认值；
    auto 或未知组合回退到默认尺寸（图片 1024×1024，视频 1280×720）。
    """
    normalized_mode = "video" if str(mode).lower() == "video" else "image"
    ratio = (aspect_ratio or DEFAULT_ASPECT_RATIO[normalized_mode]).strip()
    res = (resolution or DEFAULT_RESOLUTION[normalized_mode]).strip()

    table = VIDEO_SIZE_TABLE if normalized_mode == "video" else IMAGE_SIZE_TABLE
    row = table.get(res)
    if ratio == "auto" or not row:
        size = dict(DEFAULT_SIZE[normalized_mode])
    else:
        size = dict(row.get(ratio) or DEFAULT_SIZE[normalized_mode])

    return {
        "width": size["width"],
        "height": size["height"],
        "aspect_ratio": ratio,
        "resolution": res,
    }


# ---------------- 模型能力 ----------------

# 视频模型规格：按 model_id 关键字匹配，首个命中生效（与前端的顺序一致）。
_VIDEO_MODEL_SPECS: list[dict[str, Any]] = [
    {
        "match": ("2_5", "2-5", "2.5"),
        "resolutions": ["480p", "720p", "1080p"],
        "duration": {"min": 4, "max": 30, "default": 5},
    },
    {
        "match": ("fast", "mini"),
        "resolutions": ["480p", "720p"],
        "duration": {"min": 4, "max": 15, "default": 5},
    },
    {
        "match": ("seedance_2", "seedance-2", "seedance2.0"),
        "resolutions": ["480p", "720p", "1080p", "2160p"],
        "duration": {"min": 4, "max": 15, "default": 5},
    },
]

_DEFAULT_VIDEO_SPEC: dict[str, Any] = {
    "resolutions": ["480p", "720p"],
    "duration": {"min": 4, "max": 15, "default": 5},
}


def _match_video_spec(model_id: str) -> dict[str, Any]:
    lowered = (model_id or "").lower()
    for spec in _VIDEO_MODEL_SPECS:
        if any(token in lowered for token in spec["match"]):
            return spec
    return _DEFAULT_VIDEO_SPEC


def video_resolutions_for_model(model_id: str) -> list[str]:
    """视频模型支持的分辨率档位。"""
    return list(_match_video_spec(model_id)["resolutions"])


def video_duration_range(model_id: str) -> dict[str, int]:
    """视频模型支持的时长范围（秒）。"""
    return dict(_match_video_spec(model_id)["duration"])


def image_resolutions_for_model(model_id: str) -> list[str]:
    """Seedream 系列图片模型支持的分辨率档位。

    - 即梦 3.x：1K / 2K
    - Seedream 5.0 Lite：2K / 3K / 4K（不支持 1K）
    - 其余（Seedream 5.0 / 即梦 4.x）：2K / 4K
    """
    lowered = (model_id or "").lower()
    if "jimeng3" in lowered or "3.0" in lowered:
        return ["1K", "2K"]
    if "lite" in lowered:
        return ["2K", "3K", "4K"]
    return ["2K", "4K"]


def describe(mode: str, model_id: str | None = None) -> dict[str, Any]:
    """输出某内容模式下可用的比例 / 分辨率 / 时长（供工具文档与智能体自检）。"""
    normalized_mode = "video" if str(mode).lower() == "video" else "image"
    if normalized_mode == "video":
        return {
            "mode": "video",
            "aspect_ratios": VIDEO_ASPECT_RATIOS,
            "resolutions": video_resolutions_for_model(model_id) if model_id else VIDEO_RESOLUTIONS,
            "duration": video_duration_range(model_id) if model_id else {"min": 4, "max": 15, "default": 5},
            "defaults": {"aspect_ratio": "16:9", "resolution": "720p", "duration": 5},
        }
    return {
        "mode": "image",
        "aspect_ratios": IMAGE_ASPECT_RATIOS,
        "resolutions": image_resolutions_for_model(model_id) if model_id else IMAGE_RESOLUTIONS,
        "defaults": {"aspect_ratio": "1:1", "resolution": "2K", "count": 1},
    }
