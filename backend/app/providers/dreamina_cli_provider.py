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

"""即梦 CLI（本地命令行）Provider：按模型族拆分为两个 Provider。

- DreaminaSeedanceProvider：视频生成（text2video / img2video），底层 Seedance 系列模型。
- DreaminaSeedreamProvider：图片生成（text2img / img2img），底层 Seedream / 即梦图片模型。

两者共用同一个本机 `dreamina` 命令与登录态，公共的子进程执行 / 提交 / 轮询 /
下载 / 错误分类逻辑收敛在 DreaminaCliBaseProvider 基类中。

与 HTTP Provider 的差异：
- 调用方式：本地子进程（asyncio.create_subprocess_exec），非 HTTP 请求。
- 认证：复用本机 OAuth 登录态（~/.dreamina_cli/），api_key 留空；
  base_url 复用为 CLI 可执行路径（默认 "dreamina"，依赖 PATH）。
- 输入素材：CLI 只接受本地文件路径，image_bytes 物化为临时文件。
- 异步语义：submit 返回 submit_id，provider 自轮询 query_result（不带 CLI --poll）。
- 结果获取：query_result --download_dir 落盘后读文件字节。

CLI 输出为 JSON：{submit_id, gen_status, fail_reason,
result_json:{videos|images:[{path}]}, credit_count}。
gen_status 终态：success / fail；进行中：querying。
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

# ============================== Seedance（视频）模型映射 ==============================
# task.model_id -> CLI --model_version 参数值（数据驱动，便于扩展）
VIDEO_MODEL_MAP: dict[str, str] = {
    "seedance2.5": "seedance2.5",
    "seedance2.0mini": "seedance2.0mini",
    "seedance2.0_vip": "seedance2.0_vip",
    "seedance2.0fast": "seedance2.0fast",
    "seedance2.0": "seedance2.0",
}
DEFAULT_VIDEO_MODEL = "seedance2.5"

# (width, height) -> video_resolution 反查表（与 Seedance 对齐的子集，未命中则省略由 CLI 取默认）
_VIDEO_RESOLUTION_REVERSE: dict[tuple[int, int], str] = {
    (864, 480): "480p",
    (736, 544): "480p",
    (640, 640): "480p",
    (544, 736): "480p",
    (480, 864): "480p",
    (1248, 704): "720p",
    (1120, 832): "720p",
    (960, 960): "720p",
    (832, 1120): "720p",
    (704, 1248): "720p",
    (1920, 1088): "1080p",
    (1664, 1248): "1080p",
    (1440, 1440): "1080p",
    (1248, 1664): "1080p",
    (1088, 1920): "1080p",
}

# ============================== Seedream（图片）参数映射 ==============================
DEFAULT_IMAGE_MODEL = "seedream5.0"

# task.model_id -> CLI --model_version 参数值（即梦图片模型版本号，由 CLI 严格校验）
IMAGE_MODEL_MAP: dict[str, str] = {
    "seedream5.0": "5.0",
    "seedream5.0pro": "5.0Pro",
    "seedream5.0lite": "5.0lite",
    "jimeng4.0": "4.0",
    "jimeng3.1": "3.1",
    "jimeng3.0": "3.0",
}

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


def _image_resolution_type(width: int, height: int) -> str:
    """由宽高推导 CLI --resolution_type：按最长边映射到 1080p / 2k / 4k。"""
    m = max(int(width), int(height))
    if m <= 1280:
        return "1080p"
    if m <= 2200:
        return "2k"
    return "4k"


# 声明式错误模式表：(正则, 类别, 修复建议)。匹配 stdout+stderr 合并文本。
_ERROR_PATTERNS: list[tuple[str, str, str]] = [
    (r"未登录|not logged in|unauthorized|请先登录", "auth",
     "请在终端执行 dreamina login 重新登录（需手动在浏览器完成授权）"),
    (r"AigcComplianceConfirmationRequired", "compliance",
     "请先在即梦 Web 端完成对应模型的合规授权确认后重试"),
    (r"积分不足|insufficient|会员|credit", "quota",
     "请在即梦网页端确认账户会员等级与剩余积分"),
    (r"网页端完成第一次生成|网页端.*首次", "first_gen",
     "该生成能力需先在即梦网页端完成一次生成后才能在 CLI 使用"),
]

# gen_status 终态与失败态
_STATUS_SUCCESS = "success"
_STATUS_FAIL = "fail"
_STATUS_PROGRESS = {"querying", "pending", "running", ""}

_OUTPUT_SNIPPET = 300  # 错误信息中附带原始输出的最大长度


class DreaminaCliBaseProvider(BaseProvider):
    """即梦 CLI Provider 基类：子进程执行、提交/轮询/下载、错误分类等公共逻辑。

    子类需实现：
    - SUPPORTED_TYPES / _RESULT_ITEMS_KEY / _default_mime
    - _build_submit_args：组装生成命令的参数
    - 四个生成入口方法中各自支持的类型
    """

    SUPPORTED_TYPES: list[str] = []
    # query_result 结果 JSON 中产物列表的键（videos / images）
    _RESULT_ITEMS_KEY = "videos"

    _CMD_TIMEOUT = 60.0          # 单次 CLI 命令超时（秒）
    _POLL_INTERVAL = 10.0        # query_result 轮询间隔（秒）
    _POLL_TIMEOUT = 540.0        # 轮询总超时（秒），对齐 Celery soft time limit
    _SUBMIT_MAX_RETRIES = 2      # submit 阶段瞬时故障最多重试次数
    _CLI_CHECK_TTL = 60.0        # CLI 可用性探测缓存（秒）

    def __init__(
        self,
        base_url: str = "dreamina",
        api_key: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        # base_url 复用为 CLI 可执行文件路径；空则回退默认命令名
        self.cli_path = (base_url or "").strip() or "dreamina"
        self.config = config or {}
        self._cli_checked_at = 0.0  # CLI 可用性探测的时间戳（0 = 未探测）
        self._resolved_exec: str | None = None  # 解析到的可执行文件路径缓存

    def _resolve_exec(self) -> str:
        """解析实际可执行的 CLI 路径。

        worker 进程可能在 CLI 安装前启动（PATH 未含安装目录），
        因此默认命令名找不到时回退到常见安装位置。
        """
        if self._resolved_exec:
            return self._resolved_exec
        if self.cli_path != "dreamina" and os.path.exists(os.path.expanduser(self.cli_path)):
            self._resolved_exec = self.cli_path
            return self._resolved_exec
        import shutil
        found = shutil.which(self.cli_path)
        if found:
            self._resolved_exec = found
            return found
        for rel in (
            "~/.local/bin/dreamina",
            "~/.dreamina_cli/bin/dreamina",
            "/usr/local/bin/dreamina",
            "/usr/bin/dreamina",
        ):
            p = os.path.expanduser(rel)
            if os.path.isfile(p):
                self._resolved_exec = p
                return p
        # 未命中也返回原值，由调用时的 FileNotFoundError 统一报错
        return self.cli_path

    # ---- 子进程执行 ----
    async def _run_cli(self, args: list[str]) -> tuple[int, str]:
        """执行 dreamina 子命令，返回 (returncode, stdout+stderr 合并文本)。

        参数数组传递避免 shell 解析与路径转义；FileNotFoundError 转为「未安装」；
        超时抛 asyncio.TimeoutError 由调用方按阶段分类。
        """
        argv = [self._resolve_exec(), *args]
        logger.debug("dreamina exec: %s", " ".join(argv))
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            self._resolved_exec = None  # 清除缓存，下次重新解析
            raise ProviderError(
                f"未找到 dreamina 命令（路径: {self.cli_path}）。"
                "可在 设置 → 服务管理 → 即梦 CLI 中一键安装，或手动执行 "
                "curl -fsSL https://jimeng.jianying.com/cli | bash；"
                "也可在 Provider 配置的「Base URL / CLI 路径」中填写正确的可执行文件路径"
            ) from e

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self._CMD_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        out = stdout_b.decode("utf-8", errors="replace")
        err = stderr_b.decode("utf-8", errors="replace")
        combined = out if not err else f"{out}\n{err}".strip()
        logger.debug("dreamina exit=%s output=%s", proc.returncode, combined[:_OUTPUT_SNIPPET])
        return proc.returncode or 0, combined

    # ---- 输出解析与错误分类 ----
    @staticmethod
    def _snippet(text: str) -> str:
        return text[:_OUTPUT_SNIPPET].strip()

    def _classify_error(self, output: str) -> str | None:
        """按错误模式表分类；命中返回 (类别 + 修复建议) 的用户可见信息，未命中返回 None。"""
        for pattern, _category, fix in _ERROR_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                return fix
        return None

    def _parse_json(self, output: str, context: str) -> dict[str, Any]:
        """解析 CLI 的 JSON 输出；失败给出「升级 CLI」的可操作提示。"""
        text = output.strip()
        # CLI 正常应输出纯 JSON；容错截取第一个 { 之后的内容（防御终端提示污染）
        start = text.find("{")
        if start > 0:
            text = text[start:]
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(
                f"无法解析 dreamina {context} 输出（可能 CLI 版本不兼容），"
                f"请运行 curl -fsSL https://jimeng.jianying.com/cli | bash 升级后重试。"
                f"原始输出：{self._snippet(output)}"
            ) from e
        if not isinstance(data, dict):
            raise ProviderError(
                f"dreamina {context} 输出非预期 JSON 对象：{self._snippet(output)}"
            )
        return data

    def _fail_with_classification(self, context: str, output: str, submit_id: str | None = None) -> None:
        """对一次失败的 CLI 调用做错误分类并抛 ProviderError（总是抛出）。"""
        fix = self._classify_error(output)
        if fix:
            raise ProviderError(f"即梦 CLI {context} 失败：{self._snippet(output)}。{fix}", submit_id=submit_id)
        raise ProviderError(
            f"即梦 CLI {context} 失败：{self._snippet(output)}"
            f"（可查看 ~/.dreamina_cli/logs/ 排查）",
            submit_id=submit_id,
        )

    # ---- 前置检查 ----
    async def _ensure_cli_available(self) -> None:
        """探测 CLI 可用性与登录态（带 TTL 缓存，避免每次任务都 fork 探测）。"""
        now = time.monotonic()
        if now - self._cli_checked_at < self._CLI_CHECK_TTL:
            return
        try:
            code, out = await self._run_cli(["user_credit"])
        except asyncio.TimeoutError as e:
            raise ProviderError(f"dreamina user_credit 执行超时（{int(self._CMD_TIMEOUT)}s），请检查 CLI 是否可用") from e
        if code != 0:
            self._fail_with_classification("user_credit", out)
        # 登录态有效且能返回积分信息
        self._cli_checked_at = now

    # ---- submit / 轮询 / 下载 ----
    async def _submit(self, args: list[str]) -> str:
        """提交生成任务，返回 submit_id。对瞬时故障做有限重试。"""
        last_err: ProviderError | None = None
        for attempt in range(self._SUBMIT_MAX_RETRIES + 1):
            try:
                code, out = await self._run_cli(args)
            except asyncio.TimeoutError as e:
                last_err = ProviderError(f"即梦 CLI submit 命令执行超时（{int(self._CMD_TIMEOUT)}s）")
                if attempt == self._SUBMIT_MAX_RETRIES:
                    raise last_err from e
                continue

            if code != 0:
                # 分类错误（auth/quota/compliance）不重试；未分类非零退出码重试一次
                fix = self._classify_error(out)
                if fix or attempt == self._SUBMIT_MAX_RETRIES:
                    self._fail_with_classification("提交任务", out)
                last_err = ProviderError(f"即梦 CLI 提交任务失败（exit={code}）：{self._snippet(out)}")
                continue

            data = self._parse_json(out, "提交任务")
            submit_id = data.get("submit_id")
            status = data.get("gen_status", "")
            if status == _STATUS_FAIL:
                reason = data.get("fail_reason") or "未知原因"
                fix = self._classify_error(reason)
                msg = f"即梦 CLI 提交任务失败：{reason}" + (f"。{fix}" if fix else "")
                raise ProviderError(msg, submit_id=str(submit_id) if submit_id else None)
            if not submit_id:
                raise ProviderError(f"即梦 CLI 提交任务未返回 submit_id：{self._snippet(out)}")
            logger.info("dreamina task submitted: submit_id=%s", submit_id)
            return str(submit_id)

        # 理论上不会到达（循环内已 return/raise），兜底
        raise last_err or ProviderError("即梦 CLI 提交任务失败")

    async def _query_once(self, submit_id: str, download_dir: str | None = None) -> dict[str, Any]:
        """执行一次 query_result，返回解析后的 JSON。瞬时错误抛 TimeoutError 由轮询循环跳过。"""
        args = ["query_result", f"--submit_id={submit_id}"]
        if download_dir:
            args.append(f"--download_dir={download_dir}")
        code, out = await self._run_cli(args)
        if code != 0:
            self._fail_with_classification(f"查询任务 {submit_id}", out, submit_id=submit_id)
        return self._parse_json(out, f"查询任务 {submit_id}")

    async def _poll(self, submit_id: str) -> dict[str, Any]:
        """轮询任务直到终态，返回成功的 query_result JSON。

        单次查询超时跳过本轮（瞬时故障）；总超时/任务 fail 抛带 submit_id 的 ProviderError。
        """
        elapsed = 0.0
        while elapsed < self._POLL_TIMEOUT:
            try:
                data = await self._query_once(submit_id)
            except asyncio.TimeoutError:
                logger.warning("dreamina query_result 超时，跳过本轮: submit_id=%s", submit_id)
            else:
                status = data.get("gen_status", "")
                if status == _STATUS_SUCCESS:
                    return data
                if status == _STATUS_FAIL:
                    reason = data.get("fail_reason") or "未知原因"
                    fix = self._classify_error(reason)
                    msg = f"即梦任务 {submit_id} 生成失败：{reason}" + (f"。{fix}" if fix else "")
                    raise ProviderError(msg, submit_id=submit_id)
                # querying 等进行中状态：继续轮询
            await asyncio.sleep(self._POLL_INTERVAL)
            elapsed += self._POLL_INTERVAL
        raise ProviderError(
            f"即梦任务 {submit_id} 等待超时（>{int(self._POLL_TIMEOUT)}s）。"
            "重试该任务将从 submit_id 断点续查，不会重复扣除积分",
            submit_id=submit_id,
        )

    def _model_label(self) -> str | None:
        """结果元数据中记录的模型名；默认取配置中的 model_id，子类可覆盖。"""
        return self.config.get("model_id")

    def _default_mime(self, path: str) -> str:
        """根据产物文件后缀推断 MIME；子类可覆盖兜底值。"""
        raise NotImplementedError

    async def _download_result(self, submit_id: str, tmpdir: str) -> tuple[bytes, str, dict[str, Any]]:
        """下载结果到 tmpdir，读取产物字节、MIME 与结果元数据。"""
        data = await self._query_once(submit_id, download_dir=tmpdir)
        if data.get("gen_status") != _STATUS_SUCCESS:
            raise ProviderError(
                f"即梦任务 {submit_id} 下载结果时状态异常：{data.get('gen_status')}",
                submit_id=submit_id,
            )
        result = data.get("result_json") or {}
        items = result.get(self._RESULT_ITEMS_KEY) or []
        if not items:
            raise ProviderError(f"即梦任务 {submit_id} 成功但未返回生成结果", submit_id=submit_id)
        file_path = items[0].get("path")
        if not file_path or not os.path.isfile(file_path):
            raise ProviderError(
                f"即梦任务 {submit_id} 结果文件未下载到本地：{self._snippet(json.dumps(items, ensure_ascii=False))}",
                submit_id=submit_id,
            )
        file_bytes = Path(file_path).read_bytes()

        metadata: dict[str, Any] = {"task_id": submit_id}
        model_id = self._model_label()
        if model_id:
            metadata["model"] = model_id
        for k in ("width", "height", "duration"):
            if k in items[0]:
                metadata[k] = items[0][k]
        credit = data.get("credit_count")
        if isinstance(credit, (int, float)) and credit >= 0:
            metadata["tokens_used"] = int(credit)
        return file_bytes, self._default_mime(file_path), metadata

    # ---- 主流程 ----
    def _build_submit_args(self, kwargs: dict[str, Any], input_paths: list[str]) -> list[str]:
        """组装生成命令参数；由子类按模型族实现。"""
        raise NotImplementedError

    async def _generate(self, kwargs: dict[str, Any], input_images: list[bytes] | None) -> GenerationResult:
        await self._ensure_cli_available()

        # 断点续查：已有 submit_id 则跳过 submit 直接轮询
        resume_id = kwargs.get("submit_id")
        with tempfile.TemporaryDirectory(prefix="dreamina_cli_") as tmpdir:
            if resume_id:
                logger.info("dreamina 断点续查: submit_id=%s", resume_id)
                submit_id = str(resume_id)
            else:
                input_paths: list[str] = []
                for i, img in enumerate(input_images or []):
                    p = os.path.join(tmpdir, f"input_{i}.png")
                    Path(p).write_bytes(img)
                    input_paths.append(p)
                submit_args = self._build_submit_args(kwargs, input_paths)
                submit_id = await self._submit(submit_args)

            await self._poll(submit_id)
            file_bytes, mime_type, metadata = await self._download_result(submit_id, tmpdir)

        return GenerationResult(file_bytes=file_bytes, mime_type=mime_type, metadata=metadata)

    # ---- BaseProvider 接口 ----
    async def test_connection(self) -> bool:
        """验证 CLI 已安装且登录态有效（user_credit 可返回积分信息）。"""
        try:
            code, out = await self._run_cli(["user_credit"])
        except asyncio.TimeoutError as e:
            raise ProviderError(f"dreamina user_credit 执行超时（{int(self._CMD_TIMEOUT)}s）") from e
        if code != 0:
            self._fail_with_classification("user_credit", out)
        # 确认能解析出积分信息（登录态有效的标志）
        data = self._parse_json(out, "user_credit")
        if "total_credit" not in data and "vip_credit" not in data:
            raise ProviderError(f"dreamina user_credit 返回异常：{self._snippet(out)}")
        self._cli_checked_at = time.monotonic()
        return True


class DreaminaSeedanceProvider(DreaminaCliBaseProvider):
    """即梦 CLI 视频生成 Provider（Seedance 系列模型，本地子进程调用）。"""

    SUPPORTED_TYPES = ["text2video", "img2video"]
    _RESULT_ITEMS_KEY = "videos"

    def _model_label(self) -> str | None:
        return self.config.get("model_id") or DEFAULT_VIDEO_MODEL

    def _default_mime(self, path: str) -> str:
        return "video/mp4"

    def _resolve_model(self, kwargs: dict[str, Any]) -> str:
        model_id = kwargs.get("model_id") or self.config.get("model_id") or DEFAULT_VIDEO_MODEL
        if model_id not in VIDEO_MODEL_MAP:
            supported = "、".join(VIDEO_MODEL_MAP.keys())
            raise ProviderError(f"即梦 Seedance（CLI）不支持模型 {model_id}，支持的模型：{supported}")
        return VIDEO_MODEL_MAP[model_id]

    def _build_submit_args(self, kwargs: dict[str, Any], input_paths: list[str]) -> list[str]:
        model_version = self._resolve_model(kwargs)
        args: list[str] = []
        if input_paths:
            args.append("image2video")
            args.append(f"--image={input_paths[0]}")
        else:
            args.append("text2video")

        prompt = kwargs.get("prompt", "")
        if prompt:
            args.append(f"--prompt={prompt}")
        duration = kwargs.get("duration")
        if duration is not None:
            args.append(f"--duration={int(duration)}")
        args.append(f"--model_version={model_version}")

        width, height = kwargs.get("width"), kwargs.get("height")
        if width is not None and height is not None:
            resolution = _VIDEO_RESOLUTION_REVERSE.get((int(width), int(height)))
            if resolution:
                args.append(f"--video_resolution={resolution}")
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
        return await self._generate(kwargs, input_images=[image_bytes])

    async def text_to_image(self, prompt: str, **kwargs: Any) -> GenerationResult:
        raise ProviderError("即梦 Seedance（CLI）仅支持视频生成，图片请使用即梦 Seedream（CLI）")

    async def image_to_image(self, image_bytes: list[bytes], prompt: str, **kwargs: Any) -> GenerationResult:
        raise ProviderError("即梦 Seedance（CLI）仅支持视频生成，图片请使用即梦 Seedream（CLI）")


class DreaminaSeedreamProvider(DreaminaCliBaseProvider):
    """即梦 CLI 图片生成 Provider（Seedream / 即梦图片模型，本地子进程调用）。"""

    SUPPORTED_TYPES = ["text2img", "img2img"]
    _RESULT_ITEMS_KEY = "images"

    _POLL_TIMEOUT = 300.0  # 图片生成通常远快于视频，缩短轮询总超时

    def _default_mime(self, path: str) -> str:
        return _IMAGE_MIME_BY_SUFFIX.get(Path(path).suffix.lower(), "image/png")

    def _resolve_model(self, kwargs: dict[str, Any]) -> str:
        """把应用内的 model_id 映射为 CLI 期望的版本号；未命中时原样透传。"""
        model_id = str(kwargs.get("model_id") or self.config.get("model_id") or DEFAULT_IMAGE_MODEL)
        return IMAGE_MODEL_MAP.get(model_id, model_id)

    def _build_submit_args(self, kwargs: dict[str, Any], input_paths: list[str]) -> list[str]:
        args: list[str] = []
        if input_paths:
            args.append("image2image")
            args.append(f"--images={','.join(input_paths)}")
        else:
            args.append("text2image")

        prompt = kwargs.get("prompt", "")
        if prompt:
            args.append(f"--prompt={prompt}")
        args.append(f"--model_version={self._resolve_model(kwargs)}")

        width, height = kwargs.get("width"), kwargs.get("height")
        if width is not None and height is not None:
            args.append(f"--ratio={_ratio_from_size(width, height)}")
            args.append(f"--resolution_type={_image_resolution_type(width, height)}")
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
