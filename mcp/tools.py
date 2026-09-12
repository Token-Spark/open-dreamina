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

"""工具注册表：把 handlers 暴露为 MCP 工具（name / description / inputSchema）。

描述文案即智能体的使用说明书，尽量把「何时用、必填什么、失败怎么修」写进 description，
减少智能体试错与猜测字段名的成本。
"""
from __future__ import annotations

from typing import Any

from . import catalog, sizes
from .handlers import HANDLERS

# ---------------- 可复用片段 ----------------

_PROVIDER = {
    "type": "string",
    "description": "模型服务 slug（如 seedream / seedance-2-5 / openai），也可传 Provider id。"
    "用 list_providers 查看已配置项；未配置的 slug 需先在 Web 界面「设置 → 服务管理」录入 API Key。",
}
_MODEL_ID = {
    "type": "string",
    "description": "服务下的模型 id，省略则用该服务默认模型。用 list_models 查看可选值与能力。",
}
_CONVERSATION_ID = {
    "type": "string",
    "description": "归属对话 id。省略时后端会自动新建对话，并在返回值 conversation_id 中给出。",
}
_PROMPT = {"type": "string", "description": "正向提示词，建议描述主体 + 场景 + 光线 + 镜头 + 风格。"}

_REFERENCE_PROPS: dict[str, Any] = {
    "reference_asset_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "已有素材的 asset_id 列表；传入后任务类型自动切换为 img2img / img2video。",
    },
    "reference_paths": {
        "type": "array",
        "items": {"type": "string"},
        "description": "本地图片路径（绝对路径）；工具会先上传再引用，可与 reference_asset_ids 同时使用。",
    },
}

_SIZE_PROPS: dict[str, Any] = {
    "aspect_ratio": {
        "type": "string",
        "description": f"画面比例。图片可选 {'、'.join(sizes.IMAGE_ASPECT_RATIOS)}；"
        f"视频可选 {'、'.join(sizes.VIDEO_ASPECT_RATIOS)}。省略用默认值（图片 1:1，视频 16:9）。",
    },
    "resolution": {
        "type": "string",
        "description": f"分辨率档位。图片可选 {'、'.join(sizes.IMAGE_RESOLUTIONS)}；"
        f"视频可选 {'、'.join(sizes.VIDEO_RESOLUTIONS)}。由本工具换算成后端 width/height。",
    },
    "width": {"type": "integer", "description": "直接指定宽度（像素）；与 height 同时给出时忽略比例与分辨率。"},
    "height": {"type": "integer", "description": "直接指定高度（像素）；需与 width 同时给出。"},
}

_IMAGE_PARAM_PROPS: dict[str, Any] = {
    "negative_prompt": {"type": "string", "description": "负面提示词，描述要排除的内容。"},
    "count": {"type": "integer", "minimum": 1, "maximum": 4, "description": "生成张数（1~4，默认 1）。"},
    "steps": {"type": "integer", "minimum": 1, "maximum": 80, "description": "采样步数（1~80）。"},
    "guidance_scale": {
        "type": "number",
        "minimum": 1,
        "maximum": 20,
        "description": "提示词权重（1~20，默认 7）。注意后端字段名为 guidance_scale。",
    },
    "seed": {"type": "integer", "description": "随机种子；显式指定可复现同一结果。"},
    "strength": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "description": "图生图重绘强度（0~1，默认 0.7）；仅带参考素材时生效。",
    },
}

_VIDEO_PARAM_PROPS: dict[str, Any] = {
    "negative_prompt": {"type": "string", "description": "负面提示词，描述要排除的内容。"},
    "duration": {
        "type": "integer",
        "description": "视频时长（秒）。Seedance 2.5 支持 4~30；Fast/Mini 与 2.0 支持 4~15，默认 5。",
    },
    "seed": {"type": "integer", "description": "随机种子；显式指定可复现同一结果。"},
    "frame_mode": {
        "type": "string",
        "enum": ["first", "first_last", "reference"],
        "description": "参考图用法：first=首帧；first_last=首尾帧（需 2 张参考图）；reference=内容参考。省略则按普通图生视频。",
    },
}

_TASK_ID = {"type": "string", "description": "任务 id（generate_* / create_task 返回的 task_id）。"}

_PAGE = {
    "page": {"type": "integer", "minimum": 1, "description": "页码，从 1 开始（默认 1）。"},
    "page_size": {"type": "integer", "minimum": 1, "maximum": 200, "description": "每页条数（默认 20，上限 200）。"},
}


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """组装单个工具定义；handler 从 HANDLERS 绑定，避免两处维护。"""
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties, "required": required},
        "handler": HANDLERS[name],
    }


# ---------------- 工具定义 ----------------

TOOLS: list[dict[str, Any]] = [
    _tool(
        "generate_image",
        "生成图片（文生图 / 图生图）。传入 reference_asset_ids 或 reference_paths 时自动走图生图。"
        "只返回 task_id 与初始状态，需再用 wait_task 等待完成、result_urls_absolute 取图。",
        {
            "provider": _PROVIDER,
            "model_id": _MODEL_ID,
            "prompt": _PROMPT,
            **_IMAGE_PARAM_PROPS,
            **_SIZE_PROPS,
            **_REFERENCE_PROPS,
            "conversation_id": _CONVERSATION_ID,
        },
        ["provider", "prompt"],
    ),
    _tool(
        "generate_video",
        "生成视频（文生视频 / 图生视频）。传入 reference_asset_ids 或 reference_paths 时自动走图生视频，"
        "可用 frame_mode 指定首帧 / 首尾帧 / 内容参考。只返回 task_id，需再用 wait_task 等待完成。",
        {
            "provider": _PROVIDER,
            "model_id": _MODEL_ID,
            "prompt": _PROMPT,
            **_VIDEO_PARAM_PROPS,
            **_SIZE_PROPS,
            **_REFERENCE_PROPS,
            "conversation_id": _CONVERSATION_ID,
        },
        ["provider", "prompt"],
    ),
    _tool(
        "create_task",
        "通用任务创建入口，用于 generate_image / generate_video 未覆盖的场景（需完全自定义 type 或 params）。"
        "常规图片、视频生成请优先用 generate_image / generate_video。",
        {
            "type": {"type": "string", "enum": ["text2img", "img2img", "text2video", "img2video"], "description": "任务类型。"},
            "provider": _PROVIDER,
            "model_id": _MODEL_ID,
            "prompt": _PROMPT,
            "params": {
                "type": "object",
                "description": "直接透传给后端的参数对象；白名单外的字段会被后端忽略。"
                f"白名单：{'、'.join(catalog.PARAM_WHITELIST)}。",
            },
            **_IMAGE_PARAM_PROPS,
            **_VIDEO_PARAM_PROPS,
            **_SIZE_PROPS,
            **_REFERENCE_PROPS,
            "conversation_id": _CONVERSATION_ID,
        },
        ["type", "provider"],
    ),
    _tool(
        "upload_asset",
        "上传本地文件（图片）为参考素材，返回 asset_id；把该 id 放入 generate_image / generate_video 的 "
        "reference_asset_ids 即可作为参考图。也可跳过本工具，直接用 reference_paths 传本地路径。",
        {"file_path": {"type": "string", "description": "本地文件绝对路径。"}},
        ["file_path"],
    ),
    _tool(
        "get_task",
        "查询单个任务的当前状态与结果地址。终态为 completed / failed / cancelled；未完成时用 wait_task 更省事。",
        {"task_id": _TASK_ID},
        ["task_id"],
    ),
    _tool(
        "list_tasks",
        "分页查询任务列表，可按状态、类型筛选。用于回顾历史生成记录或排查失败任务。",
        {
            "status": {"type": "string", "description": "按状态筛选，多个用英文逗号分隔（如 pending,running）。"},
            "type": {"type": "string", "description": "按任务类型筛选（text2img / img2img / text2video / img2video）。"},
            **_PAGE,
        },
        [],
    ),
    _tool(
        "wait_task",
        "轮询任务直到终态（completed / failed / cancelled）或超时，是「生成后取结果」的推荐用法。"
        "超时不算失败，返回 timed_out=true，可再次调用继续等待。",
        {
            "task_id": _TASK_ID,
            "interval_seconds": {"type": "number", "description": "轮询间隔秒数（默认 3，最小 1）。"},
            "timeout_seconds": {
                "type": "number",
                "description": "本次等待上限秒数（默认 600，上限 1800）。视频生成耗时较长，建议 ≥600。",
            },
        },
        ["task_id"],
    ),
    _tool(
        "cancel_task",
        "取消尚未完成的任务（仅 pending / queued / running 可取消；已进入终态的任务会返回错误）。",
        {"task_id": _TASK_ID},
        ["task_id"],
    ),
    _tool(
        "retry_task",
        "重试失败的任务（仅 status=failed 可用），返回重新入队的任务信息。",
        {"task_id": _TASK_ID},
        ["task_id"],
    ),
    _tool(
        "create_conversation",
        "新建对话，用于把多个生成任务分组管理（类似会话）。返回对话 id，可传给 generate_* 的 conversation_id。",
        {"title": {"type": "string", "description": "对话标题；省略则后端使用「新对话」。"}},
        [],
    ),
    _tool("list_conversations", "列出全部对话，含消息数、最后一条提示词与缩略图。", {}, []),
    _tool(
        "get_conversation",
        "查看单个对话详情；include_messages 为真（默认）时附带该对话下的任务列表。",
        {
            "conversation_id": {"type": "string", "description": "对话 id。"},
            "include_messages": {"type": "boolean", "description": "是否附带任务列表（默认 true）。"},
        },
        ["conversation_id"],
    ),
    _tool(
        "update_conversation",
        "重命名对话。",
        {
            "conversation_id": {"type": "string", "description": "对话 id。"},
            "title": {"type": "string", "description": "新标题，不能为空。"},
        },
        ["conversation_id", "title"],
    ),
    _tool(
        "delete_conversation",
        "删除对话。注意：只删除对话分组，其下任务与已生成素材会保留。",
        {"conversation_id": {"type": "string", "description": "对话 id。"}},
        ["conversation_id"],
    ),
    _tool(
        "list_templates",
        "列出提示词模板（含 prompt_text / negative_prompt / params），供「按模板优化提示词」时取用。",
        {"category": {"type": "string", "enum": ["image", "video"], "description": "按模板分类筛选，省略返回全部。"}},
        [],
    ),
    _tool(
        "list_providers",
        "列出已配置的 Provider 与全部可接入 slug（含是否已配置、支持的模式）。生成前先用它确认 provider 取值。",
        {},
        [],
    ),
    _tool(
        "list_models",
        "列出模型服务目录：slug、模型 id、支持的任务类型、比例、分辨率、时长范围与是否已配置。"
        "不确定用哪个模型或参数时先调用本工具。",
        {
            "mode": {"type": "string", "enum": ["image", "video"], "description": "只看某一类能力，省略返回图片 + 视频。"},
            "model_id": {"type": "string", "description": "指定模型以查看其精确的分辨率 / 时长能力。"},
        },
        [],
    ),
    _tool(
        "get_health",
        "检查后端 / 数据库 / Redis / Celery worker 健康状态。任务长时间停留在 pending 时先调用本工具排查。",
        {},
        [],
    ),
]

TOOLS_BY_NAME: dict[str, dict[str, Any]] = {tool["name"]: tool for tool in TOOLS}

# 只暴露 JSON Schema 部分给 MCP 客户端（handler 是本地实现细节，不出现在 tools/list）。
TOOL_LISTINGS: list[dict[str, Any]] = [
    {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]} for t in TOOLS
]


def validate_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """边界校验：工具存在 + 必填参数齐全。缺失时给出「缺什么 + 怎么补」的明确提示。"""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        available = "、".join(TOOLS_BY_NAME)
        raise KeyError(f"未知工具 {name!r}。可用工具：{available}。")

    required = tool["inputSchema"].get("required", [])
    missing = [key for key in required if arguments.get(key) in (None, "")]
    if missing:
        raise ValueError(
            f"工具 {name} 缺少必填参数 {missing}。"
            f"必填项为 {required}；可用 list_models / list_providers 查询可用取值。"
        )
    return tool
