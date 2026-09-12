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

"""模型服务目录。

读取前端数据源 `frontend/src/config/modelServices.json`（单一事实来源），
避免在 MCP 侧重复维护服务/slug/模型清单；该文件新增服务时 MCP 自动生效。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATALOG_PATH = (
    Path(__file__).resolve().parent.parent / "frontend" / "src" / "config" / "modelServices.json"
)

TASK_TYPES = ("text2img", "img2img", "text2video", "img2video")
MODE_TASK_TYPES: dict[str, tuple[str, str]] = {
    "image": ("text2img", "img2img"),
    "video": ("text2video", "img2video"),
}

# worker.py 透传给 Provider 的参数白名单（必须与 backend/app/worker.py 保持一致）。
# 不在此列的参数会被后端静默忽略，因此 MCP 侧不再暴露冗余字段。
PARAM_WHITELIST = (
    "negative_prompt",
    "width",
    "height",
    "steps",
    "guidance_scale",
    "seed",
    "duration",
    "strength",
    "resolution",
    "count",
)

# 图生视频参考图模式（worker.py 支持）。
FRAME_MODES = ("first", "first_last", "reference")

_SERVICES_CACHE: list[dict[str, Any]] | None = None


class CatalogError(RuntimeError):
    """模型服务目录缺失或格式错误。"""


def load_services() -> list[dict[str, Any]]:
    """加载模型服务目录（首次读取后缓存）。"""
    global _SERVICES_CACHE
    if _SERVICES_CACHE is None:
        if not CATALOG_PATH.is_file():
            raise CatalogError(
                f"未找到模型服务目录：{CATALOG_PATH}。"
                "请在仓库根目录运行 MCP 服务（该文件与前端共用同一份配置）。"
            )
        try:
            data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CatalogError(f"模型服务目录 JSON 解析失败：{CATALOG_PATH}（{exc}）") from exc
        _SERVICES_CACHE = list(data.get("services") or [])
    return _SERVICES_CACHE


def find_service(slug: str) -> dict[str, Any] | None:
    """按 slug 查找服务定义。"""
    if not slug:
        return None
    return next((s for s in load_services() if s.get("slug") == slug), None)


def mode_of_task_type(task_type: str) -> str:
    """由任务类型反推内容模式。"""
    return "video" if task_type in MODE_TASK_TYPES["video"] else "image"


def task_type_for(mode: str, has_reference: bool) -> str:
    """由内容模式 + 是否带参考素材派生实际任务类型。"""
    if str(mode).lower() == "video":
        return "img2video" if has_reference else "text2video"
    return "img2img" if has_reference else "text2img"


def models_for_mode(slug: str, mode: str) -> list[dict[str, Any]]:
    """某服务在指定内容模式下可用的模型（模型 types 与该模式任务类型有交集）。"""
    service = find_service(slug)
    if not service:
        return []
    want = set(MODE_TASK_TYPES["video" if str(mode).lower() == "video" else "image"])
    return [m for m in service.get("models", []) if want.intersection(m.get("types", []))]


def describe_services(mode: str | None = None) -> list[dict[str, Any]]:
    """输出服务摘要（slug / 名称 / 模式 / 模型 / 默认地址），供智能体选型。"""
    result: list[dict[str, Any]] = []
    for service in load_services():
        if mode and str(mode).lower() not in [m.lower() for m in service.get("modes", [])]:
            continue
        fields = {f["key"]: f.get("default", "") for f in service.get("fields", [])}
        result.append(
            {
                "slug": service.get("slug"),
                "name": service.get("name"),
                "vendor": service.get("vendor"),
                "modes": service.get("modes", []),
                "default_base_url": fields.get("base_url", ""),
                "requires_api_key": any(
                    f["key"] == "api_key" and f.get("required") for f in service.get("fields", [])
                ),
                "models": [
                    {"id": m.get("id"), "label": m.get("label"), "types": m.get("types", [])}
                    for m in service.get("models", [])
                ],
            }
        )
    return result


def task_type_doc() -> dict[str, Any]:
    """任务类型与参数白名单说明（写入工具描述，避免智能体猜测字段名）。"""
    return {
        "task_types": list(TASK_TYPES),
        "param_whitelist": list(PARAM_WHITELIST),
        "frame_modes": list(FRAME_MODES),
        "note": "guidance_scale 才是后端字段名（前端界面显示为「提示词权重」）。",
    }
