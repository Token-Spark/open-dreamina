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

"""即梦画布 CLI（dreamina-canvas）Provider：按模型族拆分为两个 Provider。

- DreaminaSeedanceProvider：视频生成（text2video / img2video），底层 Seedance 系列模型。
- DreaminaSeedreamProvider：图片生成（text2img / img2img），底层 Seedream / 即梦图片模型。

官方已用「即梦画布 CLI」（命令名 dreamina-canvas，画布/节点/资源模型）替换旧版
即梦 CLI（命令名 dreamina，直连生成命令），本模块按新版契约实现：

- 认证：复用本机 OAuth 登录态（dreamina-canvas auth），api_key 留空；
  base_url 复用为 CLI 可执行路径（默认 "dreamina-canvas"，依赖 PATH）。
- 画布：生成目标是一块专用画布（默认名 Open Dreamina，可通过 config.canvas_name /
  config.canvas_id 指定），首次自动创建并复用。
- 素材：CLI 只接受画布资源引用，输入图片先 `resource upload` 换取 resourceId，
  再以 `--ref res:<uuid>` 挂到生成节点。
- 提交：`node create image|video ... --run --credit-ceiling <n>` 一次完成
  保存 → 报价 → 批准 → 运行；退出码 10 表示报价超过积分上限（节点已保存未扣费）。
- 轮询：`operation wait <submitId> --project-id <projectId>` 等待终态；
  退出码 20 表示服务端任务仍在进行，循环续查（与旧版轮询语义对齐）。
- 下载：`resource download <resourceId> --output <dir>` 落盘后读文件字节。

CLI 输出为统一 envelope：{schemaVersion, ok, data} / {schemaVersion, ok, error,
partialData?}；错误处理优先读取结构化的 error.code / error.class /
error.requiredAction，文本模式仅作兜底。
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from .base import BaseProvider, GenerationResult, ProviderError

logger = logging.getLogger(__name__)

# ============================== CLI 基础常量 ==============================

DEFAULT_CLI_NAME = "dreamina-canvas"

# CLI 可执行文件的常见安装位置（官方安装脚本默认落 ~/.local/bin）
_CLI_FALLBACK_PATHS = (
    "~/.local/bin/dreamina-canvas",
    "~/bin/dreamina-canvas",
    "/usr/local/bin/dreamina-canvas",
    "/usr/bin/dreamina-canvas",
)
# 旧版即梦 CLI 的常见位置：仅用于给出「官方已替换」的升级提示
_LEGACY_CLI_FALLBACK_PATHS = (
    "~/.local/bin/dreamina",
    "~/.dreamina_cli/bin/dreamina",
    "/usr/local/bin/dreamina",
    "/usr/bin/dreamina",
)

# 新版 CLI 全局参数：JSON 输出 + 禁用交互提示（生成在 worker 内无人值守执行）
_GLOBAL_ARGS = ("--format", "json", "--non-interactive")

# 默认积分上限（单次生成的报价上限，报价不超过该值时自动批准继续）
DEFAULT_CREDIT_CEILING = 200
# 默认专用画布名称（可在 Provider config.canvas_name 中覆盖）
DEFAULT_CANVAS_NAME = "Open Dreamina"

# gen_status / operation state 终态与进行中判定（新版 CLI 的 state 为小写字符串，
# 这里按已知枚举集合匹配，未知状态一律视为进行中继续等待，直到总超时）
_STATUS_SUCCESS = {"succeeded", "success", "completed", "complete", "done", "ok"}
_STATUS_FAIL = {"failed", "failure", "rejected", "canceled", "cancelled", "error"}
_STATUS_PROGRESS = {"", "queued", "pending", "running", "in_progress", "accepted", "unknown"}

# ============================== Seedance（视频）模型 ==============================
DEFAULT_VIDEO_MODEL = "seedance2.5"

# 应用内 video model_id 列表（用于校验请求合法性；实际传给 CLI 的 canonical 模型
# 由运行时 `model find` 解析，避免硬编码官方目录中可能变化的模型名）
_VIDEO_MODEL_IDS = (
    "seedance2.5",
    "seedance2.0mini",
    "seedance2.0_vip",
    "seedance2.0fast",
    "seedance2.0",
)

# Seedance 支持的画面比例（与 node create video --ratio 参数对齐）。
# 宽高像素组合不一定能约简为标准比例字符串（如 480×864 → 10:18 ≠ 9:16），
# 因此按最接近的浮点比值匹配，确保传给 CLI 的 --ratio 始终是合法枚举值。
_VIDEO_SUPPORTED_RATIOS: tuple[tuple[float, str], ...] = (
    (21 / 9, "21:9"),
    (16 / 9, "16:9"),
    (4 / 3, "4:3"),
    (1 / 1, "1:1"),
    (3 / 4, "3:4"),
    (9 / 16, "9:16"),
)


def _video_ratio_from_size(width: int, height: int) -> str:
    """由宽高推导 CLI --ratio：按最接近的官方支持比例匹配。

    视频像素表中的尺寸（如 480×864）经 GCD 约简后得到 10:18，
    并非 CLI 接受的 9:16，因此必须用最近匹配而非整数约简。
    """
    if width <= 0 or height <= 0:
        return "16:9"
    aspect = width / height
    return min(_VIDEO_SUPPORTED_RATIOS, key=lambda r: abs(r[0] - aspect))[1]


# ============================== Seedream（图片）参数 ==============================
DEFAULT_IMAGE_MODEL = "seedream5.0"

# 应用内图片 model_id 透传给 --model 前经 model find 解析为 canonical 模型；
# 不做白名单校验（与旧版行为一致），未知模型由服务端校验并给出明确错误。

# 常见画面比例（宽高比约简结果超出该集合时取最接近者）
_COMMON_RATIOS: tuple[tuple[int, int], ...] = (
    (1, 1), (16, 9), (9, 16), (4, 3), (3, 4), (3, 2), (2, 3), (21, 9),
)

_IMAGE_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _ratio_from_size(width: int, height: int) -> str:
    """由宽高推导 CLI --ratio 参数：优先约简为最简整数比，过大时取最接近的常见比例。"""
    w, h = int(width), int(height)
    if w <= 0 or h <= 0:
        return "1:1"
    g = math.gcd(w, h)
    rw, rh = w // g, h // g
    if rw <= 64 and rh <= 64:
        return f"{rw}:{rh}"
    aspect = w / h
    best = min(_COMMON_RATIOS, key=lambda r: abs(r[0] / r[1] - aspect))
    return f"{best[0]}:{best[1]}"


# 各图片模型支持的 --resolution 档位（键为应用内 model_id；服务端仍会按最新规格
# 重新校验，此处只在请求档位不被模型支持时回退，避免明显非法的入参）。
# 3.x 支持 1k/2k；4.x / 5.0 支持 2k/4k；5.0lite 支持 2k/3k/4k。
_IMAGE_RESOLUTION_SUPPORT: dict[str, set[str]] = {
    "jimeng3.0": {"1k", "2k"},
    "jimeng3.1": {"1k", "2k"},
    "jimeng4.0": {"2k", "4k"},
    "seedream5.0": {"2k", "4k"},
    "seedream5.0pro": {"2k", "4k"},
    "seedream5.0lite": {"2k", "3k", "4k"},
}
# 所有图片模型都支持的通用默认档位（请求档位不被模型支持时回退到它）
_DEFAULT_IMAGE_RESOLUTION = "2k"


def _image_resolution_type(
    model_id: str,
    width: int,
    height: int,
    resolution: str | None = None,
) -> str:
    """推导 CLI --resolution，只返回该模型支持的档位。

    - 优先按前端档位（1K/2K/3K/4K）映射；
    - 无档位时按最长边近似（<=1536 归 1k，其余归 2k）；
    - 请求档位不在模型支持集合时，回退到通用默认档位 2k。
    """
    supported = _IMAGE_RESOLUTION_SUPPORT.get(model_id, {"1k", "2k"})
    if resolution:
        tier = str(resolution).lower()
        if tier in supported:
            return tier
        return _DEFAULT_IMAGE_RESOLUTION
    m = max(int(width), int(height))
    requested = "1k" if m <= 1536 else "2k"
    return requested if requested in supported else _DEFAULT_IMAGE_RESOLUTION


# ============================== 错误分类 ==============================

# 声明式错误模式表：(正则, 类别, 修复建议)。优先匹配 envelope 的结构化字段
# （error.code / error.class / error.requiredAction），文本模式仅作兜底。
_ERROR_PATTERNS: list[tuple[str, str, str]] = [
    (r'auth_required|"login"|未登录|not logged in', "auth",
     "请在 设置 → 服务管理 → 即梦 CLI 重新完成登录（dreamina-canvas auth login）"),
    (r'generation_confirmation_required|"confirm"|需要积分确认', "confirm",
     "生成报价超过单次积分上限：请在 Provider 配置中调高「单次积分上限」（credit_ceiling）后重试"),
    (r'积分不足|insufficient|quota|"credit', "quota",
     "请在即梦网页端确认账户会员等级与剩余积分"),
    (r'AigcComplianceConfirmationRequired|合规', "compliance",
     "请先在即梦 Web 端完成对应模型的合规授权确认后重试"),
    (r'unknown_subcommand|unknown_command|无法识别', "upgrade",
     "官方已将即梦 CLI 替换为新版画布 CLI（dreamina-canvas）：请在 设置 → 服务管理 → 即梦 CLI 重新安装"),
]

_OUTPUT_SNIPPET = 300  # 错误信息中附带原始输出的最大长度


def _is_success_state(state: str | None) -> bool:
    return str(state or "").strip().lower() in _STATUS_SUCCESS


def _is_fail_state(state: str | None) -> bool:
    return str(state or "").strip().lower() in _STATUS_FAIL


def _is_progress_state(state: str | None) -> bool:
    return str(state or "").strip().lower() in _STATUS_PROGRESS


def _slugify_title(prompt: str, fallback: str) -> str:
    """用提示词前缀生成节点标题（新版 CLI 对 --run 的空正文节点要求显式标题）。"""
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    if text:
        return text[:24]
    return fallback


class DreaminaCliBaseProvider(BaseProvider):
    """即梦画布 CLI Provider 基类：子进程执行、画布/资源管理、提交/轮询/下载等公共逻辑。

    子类需实现：
    - SUPPORTED_TYPES / _RESULT_MIME_DEFAULT
    - _build_submit_args：组装 node create 生成命令的参数
    - 四个生成入口方法中各自支持的类型
    """

    SUPPORTED_TYPES: list[str] = []

    _CMD_TIMEOUT = 60.0            # 单次 CLI 命令超时（秒）
    _UPLOAD_TIMEOUT = 300.0        # resource upload 超时（大文件直传）
    _OP_WAIT_SLICE = 90.0          # 单次 operation wait 的 --timeout（秒）
    _OP_WAIT_PROC_TIMEOUT = 120.0  # 单次 operation wait 的进程超时（秒）
    _POLL_INTERVAL = 5.0           # operation wait 轮次之间的间隔（秒）
    _POLL_TIMEOUT = 540.0          # 轮询总超时（秒），对齐 Celery soft time limit
    _CLI_CHECK_TTL = 60.0          # CLI 可用性探测缓存（秒）
    _MODEL_RESOLVE_TTL = 600.0     # model find 解析缓存（秒）

    def __init__(
        self,
        base_url: str = DEFAULT_CLI_NAME,
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        # base_url 复用为 CLI 可执行文件路径；空则回退默认命令名
        self.cli_path = (base_url or "").strip() or DEFAULT_CLI_NAME
        self.config = config or {}
        self._cli_checked_at = 0.0  # CLI 可用性探测的时间戳（0 = 未探测）
        self._resolved_exec: str | None = None  # 解析到的可执行文件路径缓存
        self._canvas: tuple[str, str | None] | None = None  # (projectId, webUrl) 缓存
        self._model_cache: dict[tuple[str, str], tuple[float, str]] = {}

    # ---- 配置读取 ----
    def _credit_ceiling(self) -> int:
        """单次生成的积分报价上限（config.credit_ceiling，字符串/数字均可）。"""
        raw = self.config.get("credit_ceiling", self.config.get("creditCeiling"))
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            return DEFAULT_CREDIT_CEILING
        return value if value > 0 else DEFAULT_CREDIT_CEILING

    def _canvas_name(self) -> str:
        return str(self.config.get("canvas_name") or self.config.get("canvasName") or DEFAULT_CANVAS_NAME)

    def _explicit_canvas_id(self) -> str:
        return str(self.config.get("canvas_id") or self.config.get("project_id") or "").strip()

    # ---- 子进程执行 ----
    def _resolve_exec(self) -> str:
        """解析实际可执行的 CLI 路径。

        worker 进程可能在 CLI 安装前启动（PATH 未含安装目录），
        因此默认命令名找不到时回退到常见安装位置。
        """
        if self._resolved_exec:
            return self._resolved_exec
        expanded = os.path.expanduser(self.cli_path)
        if self.cli_path != DEFAULT_CLI_NAME and os.path.exists(expanded):
            self._resolved_exec = expanded
            return self._resolved_exec
        import shutil
        found = shutil.which(self.cli_path)
        if found:
            self._resolved_exec = found
            return found
        for rel in _CLI_FALLBACK_PATHS:
            p = os.path.expanduser(rel)
            if os.path.isfile(p):
                self._resolved_exec = p
                return p
        # 未命中也返回原值，由调用时的 FileNotFoundError 统一报错
        return self.cli_path

    def _missing_cli_error(self) -> ProviderError:
        legacy = next(
            (p for rel in _LEGACY_CLI_FALLBACK_PATHS if os.path.isfile(p := os.path.expanduser(rel))),
            None,
        )
        if legacy:
            return ProviderError(
                f"未找到 {DEFAULT_CLI_NAME} 命令，但检测到旧版即梦 CLI（{legacy}）。"
                "官方已将其替换为新版画布 CLI，请在 设置 → 服务管理 → 即梦 CLI 中一键安装新版，"
                "或手动执行 curl -fsSL https://jimeng.jianying.com/canvas-cli/install.sh | bash"
            )
        return ProviderError(
            f"未找到 {DEFAULT_CLI_NAME} 命令（路径: {self.cli_path}）。"
            "可在 设置 → 服务管理 → 即梦 CLI 中一键安装，或手动执行 "
            "curl -fsSL https://jimeng.jianying.com/canvas-cli/install.sh | bash；"
            "也可在 Provider 配置的「Base URL / CLI 路径」中填写正确的可执行文件路径"
        )

    async def _run_cli(self, args: list[str], timeout: float | None = None) -> tuple[int, str]:
        """执行 dreamina-canvas 子命令，返回 (returncode, stdout+stderr 合并文本)。

        参数数组传递避免 shell 解析与路径转义；FileNotFoundError 转为「未安装」；
        超时抛 asyncio.TimeoutError 由调用方按阶段分类。
        """
        argv = [self._resolve_exec(), *_GLOBAL_ARGS, *args]
        logger.debug("dreamina-canvas exec: %s", " ".join(argv))
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            self._resolved_exec = None  # 清除缓存，下次重新解析
            raise self._missing_cli_error() from e

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or self._CMD_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        out = stdout_b.decode("utf-8", errors="replace")
        err = stderr_b.decode("utf-8", errors="replace")
        combined = out if not err else f"{out}\n{err}".strip()
        logger.debug("dreamina-canvas exit=%s output=%s", proc.returncode, combined[:_OUTPUT_SNIPPET])
        return proc.returncode or 0, combined

    # ---- envelope 解析与错误分类 ----
    @staticmethod
    def _snippet(text: str) -> str:
        return text[:_OUTPUT_SNIPPET].strip()

    def _classify_error(self, output: str) -> str | None:
        """按错误模式表分类；命中返回用户可见的修复建议，未命中返回 None。"""
        for pattern, _category, fix in _ERROR_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                return fix
        return None

    def _parse_envelope(self, output: str, context: str) -> tuple[bool, dict[str, Any], dict[str, Any]]:
        """解析新版 CLI 的统一 envelope，返回 (ok, data, error)。

        解析失败给出「升级 CLI」的可操作提示；ok=false 时 error 为结构化错误对象
        （可能为空 dict，此时调用方基于原始输出分类）。
        """
        text = output.strip()
        start = text.find("{")
        if start > 0:
            text = text[start:]
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(
                f"无法解析 dreamina-canvas {context} 输出（可能 CLI 版本不兼容），"
                f"请运行 curl -fsSL https://jimeng.jianying.com/canvas-cli/install.sh | bash 升级后重试。"
                f"原始输出：{self._snippet(output)}"
            ) from e
        if not isinstance(envelope, dict):
            raise ProviderError(
                f"dreamina-canvas {context} 输出非预期 JSON 对象：{self._snippet(output)}"
            )
        ok = bool(envelope.get("ok"))
        data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
        error = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
        partial = envelope.get("partialData") if isinstance(envelope.get("partialData"), dict) else {}
        if partial:
            data.setdefault("partialData", partial)
        return ok, data, error

    def _fail_with_classification(self, context: str, output: str, submit_id: str | None = None) -> None:
        """对一次失败的 CLI 调用做错误分类并抛 ProviderError（总是抛出）。"""
        fix = self._classify_error(output)
        if fix:
            raise ProviderError(f"即梦画布 CLI {context} 失败：{self._snippet(output)}。{fix}", submit_id=submit_id)
        raise ProviderError(
            f"即梦画布 CLI {context} 失败：{self._snippet(output)}",
            submit_id=submit_id,
        )

    # ---- 前置检查 ----
    async def _ensure_cli_available(self) -> None:
        """探测 CLI 可用性与登录态（auth status 为本地只读操作，带 TTL 缓存）。"""
        now = time.monotonic()
        if now - self._cli_checked_at < self._CLI_CHECK_TTL:
            return
        code, out = await self._run_cli(["auth", "status"])
        ok, data, _error = self._parse_envelope(out, "auth status")
        if code != 0 or not ok:
            self._fail_with_classification("auth status", out)
        if not data.get("loggedIn"):
            raise ProviderError(
                "即梦画布 CLI 登录态无效，请在 设置 → 服务管理 → 即梦 CLI 完成登录"
                "（dreamina-canvas auth login）后重试"
            )
        self._cli_checked_at = now

    # ---- 画布管理 ----
    async def _ensure_canvas(self) -> tuple[str, str | None]:
        """解析生成用的画布 projectId，返回 (projectId, webUrl)。

        优先级：config 显式 canvas_id → canvas ls 匹配画布名（默认 Open Dreamina）
        → 自动创建同名画布。结果缓存在 provider 实例内。
        """
        if self._canvas:
            return self._canvas

        explicit = self._explicit_canvas_id()
        if explicit:
            self._canvas = (explicit, None)
            return self._canvas

        name = self._canvas_name()
        code, out = await self._run_cli(["canvas", "ls", "--limit", "50"])
        if code == 0:
            ok, data, _error = self._parse_envelope(out, "canvas ls")
            if ok:
                for item in data.get("items") or []:
                    if str(item.get("name") or "").strip() == name:
                        self._canvas = (str(item["projectId"]), item.get("webUrl"))
                        logger.info("dreamina-canvas 复用已有画布: %s (%s)", name, item["projectId"])
                        return self._canvas

        # 未找到：创建同名画布（官方对同名创建幂等，返回已存在的画布）
        code, out = await self._run_cli(["canvas", "create", name, "--use"])
        ok, data, _error = self._parse_envelope(out, "canvas create")
        if code != 0 or not ok:
            self._fail_with_classification("创建画布", out)
        project = data.get("project") or {}
        project_id = project.get("projectId")
        if not project_id:
            raise ProviderError(f"dreamina-canvas 创建画布未返回 projectId：{self._snippet(out)}")
        logger.info("dreamina-canvas 画布就绪: %s (%s)", name, project_id)
        self._canvas = (str(project_id), project.get("webUrl"))
        return self._canvas

    # ---- 资源上传 ----
    async def _upload_resource(self, project_id: str, path: str, index: int) -> str:
        """上传本地素材到画布项目，返回 resourceId。"""
        name = Path(path).stem or f"input_{index}"
        code, out = await self._run_cli(
            ["resource", "upload", "--project-id", project_id, "--file", path, "--name", name],
            timeout=self._UPLOAD_TIMEOUT,
        )
        ok, data, _error = self._parse_envelope(out, f"resource upload {name}")
        if code != 0 or not ok:
            self._fail_with_classification(f"上传参考素材 {name}", out)
        resource_id = data.get("resourceId")
        if not resource_id:
            raise ProviderError(f"dreamina-canvas 上传素材未返回 resourceId：{self._snippet(out)}")
        return str(resource_id)

    # ---- 模型解析 ----
    @staticmethod
    def _model_keyword_candidates(model_id: str) -> list[str]:
        """由应用内 model_id 生成 model find 的候选关键词。

        官方 canonical 模型名与 alias 的分隔风格不统一（如 seedance_2.0_fast_vip、
        seedance_2.5_draft），这里生成常见变体，交由 model find 的实时目录匹配。
        """
        base = (model_id or "").strip()
        candidates = [base]
        # 首个数字前插入空格：seedance2.5 -> seedance 2.5
        spaced = re.sub(r"([A-Za-z_])(\d)", r"\1 \2", base, count=1)
        if spaced not in candidates:
            candidates.append(spaced)
        # 点号换下划线：seedance 2.5 -> seedance_2.5 / seedance2_5
        for c in list(candidates):
            dotted = c.replace(".", "_")
            if dotted not in candidates:
                candidates.append(dotted)
        return candidates

    async def _resolve_model(self, model_id: str, media_type: str) -> str:
        """把应用内 model_id 解析为 CLI 的 canonical 模型名（model find 实时匹配）。

        config.model_map 提供 {"应用内id": "canonical"} 显式映射时直接使用；
        解析失败时回退原值透传（服务端校验会给出明确错误）。
        """
        model_map = self.config.get("model_map") or self.config.get("modelMap")
        if isinstance(model_map, dict) and model_map.get(model_id):
            return str(model_map[model_id])

        cache_key = (model_id, media_type)
        cached = self._model_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self._MODEL_RESOLVE_TTL:
            return cached[1]

        for keyword in self._model_keyword_candidates(model_id):
            code, out = await self._run_cli(
                ["model", "find", keyword, "--type", media_type]
            )
            if code != 0:
                continue
            try:
                ok, data, _error = self._parse_envelope(out, f"model find {keyword}")
            except ProviderError:
                continue
            if not ok:
                continue
            canonical = self._extract_canonical_model(data)
            if canonical:
                self._model_cache[cache_key] = (time.monotonic(), canonical)
                logger.info("dreamina-canvas 模型解析: %s -> %s", model_id, canonical)
                return canonical

        logger.warning(
            "dreamina-canvas model find 未命中 %s（--type %s），将原样透传给 --model",
            model_id, media_type,
        )
        return model_id

    @staticmethod
    def _extract_canonical_model(data: dict[str, Any]) -> str | None:
        """从 model find 的 data 中提取 canonical 模型名。

        model find 返回 {query, matchKind, matches:[...]}；matches 项的结构随版本
        演进（同形于 model list 的 items 或内嵌 generation），这里做浅层字段探测。
        """
        matches = data.get("matches") or data.get("items") or []
        for item in matches:
            if not isinstance(item, dict):
                continue
            for key in ("model", "canonicalModel", "canonical_model"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            gen = item.get("generation")
            if isinstance(gen, dict):
                value = gen.get("model")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    # ---- 提交 ----
    async def _submit(self, args_tail: list[str]) -> tuple[str, str | None, dict[str, Any]]:
        """执行 node create ... --run 提交生成，返回 (submitId, nodeId, data)。

        退出码 10 表示报价超过积分上限：节点已保存、尚未扣费，抛错并附带
        partialData 中的 submitId 供人工处理后断点续查。
        新版 CLI 每次调用都会生成新 submitId 且立即扣费，响应丢失时无法安全重放，
        因此提交阶段不做自动重试（与旧版「非分类失败重试一次」的语义不同）。
        """
        code, out = await self._run_cli(args_tail)
        ok, data, error = self._parse_envelope(out, "提交生成任务")

        if code == 10 or error.get("code") == "cli.generation_confirmation_required":
            raise ProviderError(
                "即梦生成报价超过单次积分上限（credit_ceiling），已停止提交（节点已保存、未扣费）。"
                "请在 Provider 配置中调高「单次积分上限」后重试。"
                f"原始输出：{self._snippet(out)}",
                submit_id=self._extract_submit_id(data),
            )
        if code != 0 or not ok:
            self._fail_with_classification("提交任务", out, submit_id=self._extract_submit_id(data))

        submit_id = self._extract_submit_id(data)
        if not submit_id:
            raise ProviderError(
                f"即梦画布 CLI 提交任务未返回 submitId：{self._snippet(out)}"
            )
        node_id = self._extract_node_id(data)
        logger.info("dreamina-canvas 任务已受理: submit_id=%s node_id=%s", submit_id, node_id)
        return submit_id, node_id, data

    @staticmethod
    def _iter_items(data: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for source in (data.get("items"), (data.get("partialData") or {}).get("items")):
            if isinstance(source, list):
                items.extend(x for x in source if isinstance(x, dict))
        return items

    @classmethod
    def _extract_submit_id(cls, data: dict[str, Any]) -> str | None:
        """从 node create 响应中提取 submitId（兼容 items / node.resources 两种结构）。"""
        for item in cls._iter_items(data):
            if item.get("submitId"):
                return str(item["submitId"])
        node = data.get("node") if isinstance(data.get("node"), dict) else {}
        for resource in node.get("resources") or []:
            if isinstance(resource, dict) and resource.get("submitId"):
                return str(resource["submitId"])
        return None

    @classmethod
    def _extract_node_id(cls, data: dict[str, Any]) -> str | None:
        for item in cls._iter_items(data):
            if item.get("nodeId"):
                return str(item["nodeId"])
        node = data.get("node") if isinstance(data.get("node"), dict) else {}
        if node.get("nodeId"):
            return str(node["nodeId"])
        return None

    # ---- 轮询（operation wait 断点续查）----
    async def _wait_operation(self, project_id: str, submit_id: str) -> list[dict[str, Any]]:
        """轮询 operation wait 直到任务终态，返回成功的资源列表。

        - 单次 wait 的 --timeout 为 _OP_WAIT_SLICE；退出码 20 表示服务端任务仍在
          进行，循环续查同一 submitId（与旧版轮询语义对齐，不重复扣费）。
        - 未知状态一律视为进行中，直到总超时，避免枚举演进导致误判失败。
        """
        elapsed = 0.0
        last_output = ""
        while elapsed < self._POLL_TIMEOUT:
            code, out = await self._run_cli(
                [
                    "operation", "wait", submit_id,
                    "--project-id", project_id,
                    "--timeout", f"{int(self._OP_WAIT_SLICE)}s",
                    "--interval", "5s",
                ],
                timeout=self._OP_WAIT_PROC_TIMEOUT,
            )
            last_output = out
            ok, data, error = self._parse_envelope(out, f"等待任务 {submit_id}")

            if code == 20 or error.get("class") == "operation_incomplete" or error.get("requiredAction") == "resume":
                # 本次等待窗口耗尽，服务端任务可能仍在继续：续查同一 submitId
                elapsed += self._OP_WAIT_SLICE
                if elapsed < self._POLL_TIMEOUT:
                    await asyncio.sleep(self._POLL_INTERVAL)
                continue
            if code != 0 or not ok:
                self._fail_with_classification(f"查询任务 {submit_id}", out, submit_id=submit_id)

            state = str(data.get("state") or "")
            if _is_fail_state(state):
                reason = self._extract_failure_reason(data) or state
                fix = self._classify_error(reason)
                msg = f"即梦任务 {submit_id} 生成失败：{reason}" + (f"。{fix}" if fix else "")
                raise ProviderError(msg, submit_id=submit_id)
            if _is_success_state(state):
                resources = [
                    r for r in (data.get("resources") or [])
                    if isinstance(r, dict) and _is_success_state(r.get("state"))
                ]
                if resources:
                    return resources
                failed = [
                    r for r in (data.get("resources") or [])
                    if isinstance(r, dict) and _is_fail_state(r.get("state"))
                ]
                if failed:
                    reason = self._extract_failure_reason(data) or f"资源终态 {failed[0].get('state')}"
                    fix = self._classify_error(reason)
                    msg = f"即梦任务 {submit_id} 生成失败：{reason}" + (f"。{fix}" if fix else "")
                    raise ProviderError(msg, submit_id=submit_id)
                # 操作成功但资源尚未就绪：再等一轮（资源状态可能滞后于操作状态）
                logger.info("dreamina-canvas 操作成功但资源未就绪，继续等待: submit_id=%s", submit_id)
            # 其他状态视为进行中
            elapsed += self._OP_WAIT_SLICE
            if elapsed < self._POLL_TIMEOUT:
                await asyncio.sleep(self._POLL_INTERVAL)

        raise ProviderError(
            f"即梦任务 {submit_id} 等待超时（>{int(self._POLL_TIMEOUT)}s，最后状态：{self._snippet(last_output)}）。"
            "重试该任务将从 submitId 断点续查，不会重复扣除积分",
            submit_id=submit_id,
        )

    @staticmethod
    def _extract_failure_reason(data: dict[str, Any]) -> str | None:
        """从 operation 终态数据中提取失败原因（submissionError / item.error）。"""
        submission_error = data.get("submissionError")
        if isinstance(submission_error, dict) and submission_error.get("message"):
            return str(submission_error["message"])
        for source in (data.get("items"), (data.get("partialData") or {}).get("items")):
            if not isinstance(source, list):
                continue
            for item in source:
                if isinstance(item, dict) and isinstance(item.get("error"), dict):
                    message = item["error"].get("message")
                    if message:
                        return str(message)
        return None

    # ---- 下载 ----
    async def _download_resources(
        self, project_id: str, resources: list[dict[str, Any]], tmpdir: str
    ) -> tuple[list[tuple[bytes, str]], dict[str, Any]]:
        """下载成功的资源到 tmpdir，返回 (files, resources)。"""
        files: list[tuple[bytes, str]] = []
        for resource in resources:
            resource_id = str(resource.get("resourceId") or "")
            if not resource_id:
                continue
            code, out = await self._run_cli(
                ["resource", "download", resource_id, "--project-id", project_id, "--output", tmpdir]
            )
            ok, data, _error = self._parse_envelope(out, f"下载资源 {resource_id}")
            if code != 0 or not ok:
                self._fail_with_classification(f"下载资源 {resource_id}", out)
            file_path = data.get("path")
            if not file_path or not os.path.isfile(file_path):
                raise ProviderError(
                    f"即梦资源 {resource_id} 未下载到本地：{self._snippet(out)}"
                )
            files.append((Path(file_path).read_bytes(), self._resource_mime(resource, file_path)))
        if not files:
            raise ProviderError("即梦任务成功但未返回可下载的生成结果")
        return files, resources

    def _resource_mime(self, resource: dict[str, Any], path: str) -> str:
        """优先按资源的 format 字段推断 MIME，退回子类按后缀的默认值。"""
        fmt = str(resource.get("format") or "").strip().lower()
        if fmt:
            mapping = {
                "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "mp4": "video/mp4", "mov": "video/quicktime",
                "webm": "video/webm", "mp3": "audio/mpeg", "wav": "audio/wav",
                "m4a": "audio/mp4", "flac": "audio/flac",
            }
            if fmt in mapping:
                return mapping[fmt]
        return self._default_mime(path)

    def _default_mime(self, path: str) -> str:
        """根据产物文件后缀推断 MIME；子类可覆盖兜底值。"""
        raise NotImplementedError

    # ---- 主流程 ----
    async def _build_submit_args(
        self, kwargs: dict[str, Any], project_id: str, input_paths: list[str]
    ) -> list[str]:
        """组装 node create 生成命令参数；由子类按模型族实现（内部会异步上传素材与解析模型）。"""
        raise NotImplementedError

    async def _generate(self, kwargs: dict[str, Any], input_images: list[bytes] | None) -> GenerationResult:
        await self._ensure_cli_available()
        project_id, _web_url = await self._ensure_canvas()

        # 断点续查：已有 submit_id 则跳过提交直接轮询（服务端幂等，不会重复扣费）
        resume_id = kwargs.get("submit_id")
        with tempfile.TemporaryDirectory(prefix="dreamina_canvas_cli_") as tmpdir:
            if resume_id:
                logger.info("dreamina-canvas 断点续查: submit_id=%s", resume_id)
                submit_id = str(resume_id)
                node_id = None
                submit_data: dict[str, Any] = {}
            else:
                input_paths: list[str] = []
                for i, img in enumerate(input_images or []):
                    p = os.path.join(tmpdir, f"input_{i}.png")
                    Path(p).write_bytes(img)
                    input_paths.append(p)
                submit_args = await self._build_submit_args(kwargs, project_id, input_paths)
                submit_id, node_id, submit_data = await self._submit(submit_args)

            resources = await self._wait_operation(project_id, submit_id)
            files, _ = await self._download_resources(project_id, resources, tmpdir)

        metadata: dict[str, Any] = {"task_id": submit_id, "project_id": project_id}
        if node_id:
            metadata["node_id"] = node_id
        model_id = self._model_label()
        if model_id:
            metadata["model"] = model_id
        first = resources[0] if resources else {}
        for k in ("width", "height"):
            if first.get(k):
                metadata[k] = first[k]
        # 产物时长优先取请求参数（operation 资源结构不返回时长）
        duration = kwargs.get("duration")
        if duration is not None:
            metadata["duration"] = int(duration)
        credits = self._extract_credits(submit_data)
        if credits is not None:
            metadata["tokens_used"] = credits
        if self._canvas and self._canvas[1]:
            metadata["canvas_url"] = self._canvas[1]

        return GenerationResult(
            file_bytes=files[0][0],
            mime_type=files[0][1],
            metadata=metadata,
            files=files,
        )

    @staticmethod
    def _extract_credits(data: dict[str, Any]) -> int | None:
        """从提交响应中提取积分消耗（node.resources[].creditsAmount 求和）。"""
        node = data.get("node") if isinstance(data.get("node"), dict) else {}
        total = 0
        found = False
        for resource in node.get("resources") or []:
            if isinstance(resource, dict) and isinstance(resource.get("creditsAmount"), (int, float)):
                total += int(resource["creditsAmount"])
                found = True
        return total if found else None

    def _model_label(self) -> str | None:
        """结果元数据中记录的模型名；子类可覆盖。"""
        return self.config.get("model_id")

    # ---- BaseProvider 接口 ----
    async def test_connection(self) -> bool:
        """验证 CLI 已安装且登录态有效（auth account 能返回当前账号信息）。"""
        code, out = await self._run_cli(["auth", "account"])
        ok, data, _error = self._parse_envelope(out, "auth account")
        if code != 0 or not ok:
            self._fail_with_classification("auth account", out)
        if not data.get("userId"):
            raise ProviderError(f"dreamina-canvas auth account 返回异常：{self._snippet(out)}")
        self._cli_checked_at = time.monotonic()
        return True


class DreaminaSeedanceProvider(DreaminaCliBaseProvider):
    """即梦画布 CLI 视频生成 Provider（Seedance 系列模型，本地子进程调用）。"""

    SUPPORTED_TYPES = ["text2video", "img2video"]

    def _model_label(self) -> str | None:
        return self.config.get("model_id") or DEFAULT_VIDEO_MODEL

    def _default_mime(self, path: str) -> str:
        return "video/mp4"

    async def _build_submit_args(
        self, kwargs: dict[str, Any], project_id: str, input_paths: list[str]
    ) -> list[str]:
        model_id = kwargs.get("model_id") or self.config.get("model_id") or DEFAULT_VIDEO_MODEL
        if model_id not in _VIDEO_MODEL_IDS:
            supported = "、".join(_VIDEO_MODEL_IDS)
            raise ProviderError(f"即梦 Seedance（CLI）不支持模型 {model_id}，支持的模型：{supported}")

        args: list[str] = ["node", "create", "video", "--project-id", project_id]
        # 根据参考素材数量与帧模式选择公开 mode（新版无 i2v）：
        # - first_last_frame：单图为锁比例首帧；两张有序图片为首帧 + 尾帧
        # - m2v：多模态参考（多张图 / 混合素材）
        # - t2v：无参考素材（CLI 拒绝 t2v 携带任何引用）
        if input_paths:
            if frame_mode := kwargs.get("frame_mode"):
                if frame_mode == "first_last" and len(input_paths) >= 2:
                    mode = "first_last_frame"
                elif len(input_paths) > 1:
                    mode = "m2v"
                else:
                    mode = "first_last_frame"
            elif len(input_paths) > 1:
                mode = "m2v"
            else:
                mode = "first_last_frame"
            args += ["--mode", mode]
        else:
            args += ["--mode", "t2v"]

        prompt = kwargs.get("prompt", "")
        args += ["--title", _slugify_title(prompt, f"Open Dreamina 视频 {time.strftime('%m%d%H%M%S')}")]
        if prompt:
            args += ["--prompt", prompt]
        # --model 使用运行时解析出的 canonical 模型名（model find 实时匹配官方目录）
        args += ["--model", await self._resolve_model(str(model_id), "video")]

        # 参考素材：先上传到画布项目换取 resourceId，再以 res: 协议引用。
        # 比例不传 --ratio：有参考图时输出比例由素材决定（first_last_frame 由首帧锁定）。
        for i, p in enumerate(input_paths):
            resource_id = await self._upload_resource(project_id, p, i)
            args += ["--ref", f"res:{resource_id}"]

        duration = kwargs.get("duration")
        if duration is not None:
            args += ["--duration", str(int(duration))]

        width, height = kwargs.get("width"), kwargs.get("height")
        if not input_paths and width is not None and height is not None:
            # t2v 无素材可推断比例，必须显式传入
            args += ["--ratio", _video_ratio_from_size(int(width), int(height))]
        args += ["--resolution", "720p"]

        count = int(kwargs.get("count") or 1)
        if count > 1:
            args += ["--count", str(count)]
        args += ["--run", "--credit-ceiling", str(self._credit_ceiling())]
        return args

    async def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        kwargs = {**kwargs, "prompt": prompt, "duration": duration}
        return await self._generate(kwargs, input_images=None)

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        if not image_bytes:
            raise ProviderError("即梦 Seedance（CLI）图生视频缺少输入图片")
        kwargs = {**kwargs, "prompt": prompt, "duration": duration}
        # 收集所有参考图：首帧 + 尾帧 / 多模态参考列表。
        # worker 按 frame_mode 设置 last_image_bytes / reference_image_bytes_list。
        ref_list: list[bytes] = kwargs.pop("reference_image_bytes_list", None) or []
        last_bytes = kwargs.pop("last_image_bytes", None)
        frame_mode = kwargs.get("frame_mode")
        if frame_mode == "first_last":
            if not last_bytes:
                raise ProviderError("即梦 Seedance（CLI）首尾帧模式缺少尾帧图片")
            return await self._generate(kwargs, input_images=[image_bytes, last_bytes])
        if frame_mode == "reference" and ref_list:
            return await self._generate(kwargs, input_images=ref_list)
        # 单图（首帧）模式
        return await self._generate(kwargs, input_images=[image_bytes])

    async def text_to_image(self, prompt: str, **kwargs: Any) -> GenerationResult:
        raise ProviderError("即梦 Seedance（CLI）仅支持视频生成，图片请使用即梦 Seedream（CLI）")

    async def image_to_image(self, image_bytes: list[bytes], prompt: str, **kwargs: Any) -> GenerationResult:
        raise ProviderError("即梦 Seedance（CLI）仅支持视频生成，图片请使用即梦 Seedream（CLI）")


class DreaminaSeedreamProvider(DreaminaCliBaseProvider):
    """即梦画布 CLI 图片生成 Provider（Seedream / 即梦图片模型，本地子进程调用）。"""

    SUPPORTED_TYPES = ["text2img", "img2img"]

    _POLL_TIMEOUT = 300.0  # 图片生成通常远快于视频，缩短轮询总超时

    def _default_mime(self, path: str) -> str:
        return _IMAGE_MIME_BY_SUFFIX.get(Path(path).suffix.lower(), "image/png")

    async def _build_submit_args(
        self, kwargs: dict[str, Any], project_id: str, input_paths: list[str]
    ) -> list[str]:
        model_id = str(kwargs.get("model_id") or self.config.get("model_id") or DEFAULT_IMAGE_MODEL)

        args: list[str] = ["node", "create", "image", "--project-id", project_id]
        # 图片 mode：i2i（有参考素材）/ t2i（无参考素材）
        args += ["--mode", "i2i" if input_paths else "t2i"]

        prompt = kwargs.get("prompt", "")
        args += ["--title", _slugify_title(prompt, f"Open Dreamina 图片 {time.strftime('%m%d%H%M%S')}")]
        if prompt:
            args += ["--prompt", prompt]
        # --model 使用运行时解析出的 canonical 模型名（model find 实时匹配官方目录）
        args += ["--model", await self._resolve_model(model_id, "image")]

        # 参考素材：先上传到画布项目换取 resourceId，再以 res: 协议引用
        for i, p in enumerate(input_paths):
            resource_id = await self._upload_resource(project_id, p, i)
            args += ["--ref", f"res:{resource_id}"]

        count = int(kwargs.get("count") or 1)
        if count > 1:
            args += ["--count", str(count)]

        width, height = kwargs.get("width"), kwargs.get("height")
        if width is not None and height is not None:
            args += ["--ratio", _ratio_from_size(width, height)]
            args += [
                "--resolution",
                _image_resolution_type(model_id, width, height, kwargs.get("resolution")),
            ]
        args += ["--run", "--credit-ceiling", str(self._credit_ceiling())]
        return args

    async def text_to_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 30,
        **kwargs: Any,
    ) -> GenerationResult:
        kwargs = {**kwargs, "prompt": prompt, "width": width, "height": height}
        return await self._generate(kwargs, input_images=None)

    async def image_to_image(
        self,
        image_bytes: list[bytes],
        prompt: str,
        strength: float = 0.7,
        **kwargs: Any,
    ) -> GenerationResult:
        images = [b for b in (image_bytes or []) if b]
        if not images:
            raise ProviderError("即梦 Seedream（CLI）图生图缺少输入图片")
        kwargs = {**kwargs, "prompt": prompt}
        return await self._generate(kwargs, input_images=images)

    async def text_to_video(self, prompt: str, duration: int = 5, **kwargs: Any) -> GenerationResult:
        raise ProviderError("即梦 Seedream（CLI）仅支持图片生成，视频请使用即梦 Seedance（CLI）")

    async def image_to_video(
        self,
        image_bytes: bytes,
        prompt: str = "",
        duration: int = 5,
        **kwargs: Any,
    ) -> GenerationResult:
        raise ProviderError("即梦 Seedream（CLI）仅支持图片生成，视频请使用即梦 Seedance（CLI）")


# 向后兼容：原「即梦 CLI」Provider 等价于视频侧的 Seedance Provider
DreaminaCliProvider = DreaminaSeedanceProvider
