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

"""即梦画布 CLI（dreamina-canvas）安装 / 登录引导服务（运行在 celery-worker 进程内）。

设计要点：
- CLI 必须安装在 celery-worker 所在机器（生成任务在 worker 内执行），
  因此本模块所有函数都以 Celery 任务形式调度到 worker 执行，API 层只做转发。
- 官方已用「即梦画布 CLI」（命令名 dreamina-canvas）替换旧版即梦 CLI（dreamina），
  安装脚本为 `curl -fsSL https://jimeng.jianying.com/canvas-cli/install.sh | bash`。
- 登录：`dreamina-canvas --non-interactive auth login` 返回 device flow 授权材料
  （deviceCode / userCode / verificationUriComplete），由用户在浏览器完成授权；
  完成检测以 `auth account` 能否返回账号信息为准（服务端认可的最终判据）。
- 登录会话信息临时存 Redis（TTL 30 分钟），供前端轮询。
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import redis

from ..config import settings

logger = logging.getLogger(__name__)

# 官方安装脚本（新版画布 CLI）
INSTALL_SCRIPT_URL = "https://jimeng.jianying.com/canvas-cli/install.sh"
INSTALL_SCRIPT_SHORT_URL = "https://jimeng.jianying.com/canvas-cli"
DEFAULT_CLI_NAME = "dreamina-canvas"
LEGACY_CLI_NAME = "dreamina"

_INSTALL_TIMEOUT = 600  # 安装（下载二进制）超时（秒）
_CMD_TIMEOUT = 60       # 普通 CLI 命令超时（秒）
_LOGIN_TIMEOUT = 90     # auth login --non-interactive 超时（秒）
_SNIPPET = 800          # 返回给前端的原始输出截断长度

# Redis key（沿用旧 key 前缀，避免升级后残留状态无法清理）
_INSTALLING_KEY = "dreamina_cli:installing"          # 安装进行中标记
_INSTALL_ATTEMPTS_KEY = "dreamina_cli:install_attempts"  # 自动安装尝试次数
_RESOLVED_PATH_KEY = "dreamina_cli:cli_path"         # 安装后探测到的可执行文件路径
_LOGIN_SESSION_KEY = "dreamina_cli:login_session"    # device flow 登录会话
_LOGIN_SESSION_TTL = 1800

# 安装脚本常见的二进制落点（HOME 可能已被重定向到持久化目录）
_FALLBACK_PATHS = (
    "~/.local/bin/dreamina-canvas",
    "~/bin/dreamina-canvas",
    "/usr/local/bin/dreamina-canvas",
    "/usr/bin/dreamina-canvas",
)
# 旧版 CLI 的常见位置：仅用于给出「官方已替换」的升级提示
_LEGACY_FALLBACK_PATHS = (
    "~/.local/bin/dreamina",
    "~/.dreamina_cli/bin/dreamina",
    "/usr/local/bin/dreamina",
    "/usr/bin/dreamina",
)


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


# ---- 子进程执行 ----

def _run(args: list[str], timeout: float = _CMD_TIMEOUT) -> tuple[int, str]:
    """同步执行命令，返回 (returncode, stdout+stderr)。文件缺失返回 127。"""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, f"未找到命令: {args[0]}"
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "")
        return 124, f"命令超时（{int(timeout)}s）。{str(out)[:_SNIPPET]}"
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode or 0, out.strip()


def resolve_cli_path(cli_path: str | None = None) -> str | None:
    """解析可用的 dreamina-canvas 可执行文件路径。

    顺序：显式路径 → Redis 记录的安装路径 → PATH → 常见安装位置 → bash login shell。
    """
    candidates: list[str] = []
    if cli_path and cli_path != DEFAULT_CLI_NAME:
        candidates.append(cli_path)
    try:
        saved = _redis().get(_RESOLVED_PATH_KEY)
        if saved:
            candidates.append(saved)
    except Exception:
        pass
    candidates.append(cli_path or DEFAULT_CLI_NAME)

    for c in candidates:
        # 绝对/相对路径直接验证
        if "/" in c or c.startswith("~"):
            p = Path(c).expanduser()
            if p.is_file():
                return str(p)
            continue
        found = shutil.which(c)
        if found:
            return found

    for rel in _FALLBACK_PATHS:
        p = Path(rel).expanduser()
        if p.is_file():
            return str(p)

    # 最后尝试 login shell（安装脚本通常会把 PATH 写入 ~/.bashrc）
    code, out = _run(["bash", "-lc", f"command -v {DEFAULT_CLI_NAME}"], timeout=15)
    if code == 0 and out.strip():
        return out.strip().splitlines()[-1]
    return None


def find_legacy_cli() -> str | None:
    """检测旧版即梦 CLI（dreamina）是否仍在本机：用于给出升级提示。"""
    for rel in _LEGACY_FALLBACK_PATHS:
        p = Path(rel).expanduser()
        if p.is_file():
            return str(p)
    found = shutil.which(LEGACY_CLI_NAME)
    return found or None


def _set_resolved_path(path: str) -> None:
    try:
        _redis().set(_RESOLVED_PATH_KEY, path)
    except Exception:
        pass


# ---- envelope 解析 ----

def _parse_envelope(out: str) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    """解析新版 CLI 的统一 envelope，返回 (ok, data, error)。解析失败返回 (False, {}, {})。"""
    text = out.strip()
    start = text.find("{")
    if start < 0:
        return False, {}, {}
    try:
        envelope = json.loads(text[start:])
    except json.JSONDecodeError:
        return False, {}, {}
    if not isinstance(envelope, dict):
        return False, {}, {}
    ok = bool(envelope.get("ok"))
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    error = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
    return ok, data, error


def _parse_version(out: str) -> str | None:
    """从 `dreamina-canvas version` 输出中解析版本号。

    新版输出为 envelope（data.version），兼容纯文本兜底。
    """
    ok, data, _error = _parse_envelope(out)
    if ok and data.get("version"):
        return str(data["version"])[:120]
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines[-1][:120] if lines else None


# ---- 安装 ----

def is_installing() -> bool:
    try:
        return bool(_redis().get(_INSTALLING_KEY))
    except Exception:
        return False


def _run_install_script() -> tuple[int, str, str]:
    """获取并执行官方安装脚本，返回 (returncode, output, 下载方式)。

    优先用 curl；容器镜像未装 curl 时回退到 Python urllib，避免依赖镜像里是否预装 curl。
    """
    curl = shutil.which("curl")
    if curl:
        code, out = _run(
            ["bash", "-lc", f"curl -fsSL {INSTALL_SCRIPT_URL} | bash"],
            timeout=_INSTALL_TIMEOUT,
        )
        return code, out, "curl"

    import tempfile
    import urllib.request

    try:
        req = urllib.request.Request(INSTALL_SCRIPT_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, tempfile.NamedTemporaryFile(
            mode="w+", suffix=".sh", delete=False
        ) as f:
            script = resp.read().decode("utf-8", errors="replace")
            f.write(script)
            path = f.name
        code, out = _run(["bash", path], timeout=_INSTALL_TIMEOUT)
    except Exception as e:
        return 1, f"下载安装脚本失败（Python urllib）: {type(e).__name__}: {e}", "urllib"
    finally:
        import os as _os
        if "path" in locals():
            try:
                _os.remove(path)
            except OSError:
                pass
    return code, out, "urllib"


def install_cli() -> dict[str, Any]:
    """执行官方安装脚本（幂等：已安装则直接复用 / 升级）。"""
    try:
        r = _redis()
        r.set(_INSTALLING_KEY, "1", ex=900)
    except Exception:
        r = None
    try:
        code, out, via = _run_install_script()
        resolved = resolve_cli_path()
        if resolved:
            _set_resolved_path(resolved)
        success = resolved is not None
        if success:
            message = f"即梦画布 CLI 安装成功（{via}）：{resolved}"
        elif code == 0:
            message = "安装脚本执行成功但未找到 dreamina-canvas 命令，请重新打开终端或检查 PATH"
        else:
            message = (
                f"安装脚本执行失败（exit={code}），请确认容器可访问外网，或在 worker 所在机器手动执行 "
                f"curl -fsSL {INSTALL_SCRIPT_URL} | bash"
            )
        logger.info("[即梦CLI] 安装结果: %s", message)
        return {
            "success": success,
            "message": message,
            "cli_path": resolved,
            "output": out[-_SNIPPET:],
        }
    finally:
        if r is not None:
            try:
                r.delete(_INSTALLING_KEY)
            except Exception:
                pass


# ---- 状态探测 ----

def get_status(cli_path: str | None = None) -> dict[str, Any]:
    """探测 worker 节点上 CLI 的安装 / 登录状态。

    登录态判据：`auth status` 的 data.loggedIn（本地凭据）。
    已登录时附带 `auth account` 的账号信息（userId / isVip / vipLevel）。
    """
    installing = is_installing()
    resolved = resolve_cli_path(cli_path)
    status: dict[str, Any] = {
        "installed": resolved is not None,
        "installing": installing,
        "cli_path": resolved,
        "version": None,
        "logged_in": False,
        "credit_info": None,
        "account_info": None,
        "legacy_cli": find_legacy_cli(),
        "message": "",
    }
    if not resolved:
        if installing:
            status["message"] = "正在安装…"
        elif status["legacy_cli"]:
            status["message"] = (
                "检测到旧版即梦 CLI（dreamina），官方已替换为新版画布 CLI（dreamina-canvas），请点击安装"
            )
        else:
            status["message"] = "worker 节点未检测到即梦画布 CLI"
        return status

    code, out = _run([resolved, "version"], timeout=30)
    if code == 0:
        status["version"] = _parse_version(out)

    code, out = _run([resolved, "auth", "status"], timeout=30)
    ok, data, _error = _parse_envelope(out)
    logged_in = bool(code == 0 and ok and data.get("loggedIn"))

    if logged_in:
        # 服务端认可的账号信息（VIP 等级等）；失败不影响登录态判定
        code2, out2 = _run([resolved, "auth", "account"], timeout=30)
        ok2, data2, _e2 = _parse_envelope(out2)
        if code2 == 0 and ok2 and data2.get("userId"):
            status["account_info"] = data2
        status["logged_in"] = True
        status["message"] = "CLI 已就绪（登录态有效）"
    else:
        status["message"] = "CLI 已安装但未登录（或登录态已失效），请完成登录引导"
    return status


# ---- 登录（device flow 引导流程）----

def start_login(cli_path: str | None = None) -> dict[str, Any]:
    """发起非交互登录：返回需要用户在浏览器完成的授权材料。"""
    resolved = resolve_cli_path(cli_path)
    if not resolved:
        return {"ok": False, "message": "即梦画布 CLI 尚未安装，请先完成安装步骤"}

    code, out = _run([resolved, "auth", "login"], timeout=_LOGIN_TIMEOUT)
    ok, data, _error = _parse_envelope(out)
    challenge = data.get("challenge") if isinstance(data.get("challenge"), dict) else {}
    fields: dict[str, str] = {}
    if challenge:
        device_code = str(challenge.get("deviceCode") or "")
        user_code = str(challenge.get("userCode") or "")
        # verificationUriComplete 已拼接 user_code，可直接打开授权
        verification_uri = str(
            challenge.get("verificationUriComplete") or challenge.get("verificationUri") or ""
        )
        if device_code:
            fields["device_code"] = device_code
        if user_code:
            fields["user_code"] = user_code
        if verification_uri:
            fields["verification_uri"] = verification_uri

    if not fields.get("device_code"):
        return {
            "ok": False,
            "message": "无法从 dreamina-canvas auth login 输出中解析授权信息，"
            "请在 worker 所在终端手动执行 dreamina-canvas auth login 完成登录",
            "raw_output": out[-_SNIPPET:],
        }

    session = {**fields, "cli_path": resolved}
    try:
        _redis().set(_LOGIN_SESSION_KEY, json.dumps(session, ensure_ascii=False), ex=_LOGIN_SESSION_TTL)
    except Exception:
        logger.warning("[即梦CLI] 登录会话写入 Redis 失败（不影响授权检测）")
    logger.info("[即梦CLI] device flow 登录已发起: verification_uri=%s", fields.get("verification_uri"))
    return {"ok": True, **fields, "raw_output": out[-_SNIPPET:]}


def get_login_session() -> dict[str, Any] | None:
    try:
        raw = _redis().get(_LOGIN_SESSION_KEY)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def check_login(cli_path: str | None = None) -> dict[str, Any]:
    """校验登录是否已由用户在浏览器完成。

    判据：`auth account` 能返回服务端认可的账号信息即登录成功。
    """
    session = get_login_session()
    if not session:
        return {"state": "no_session", "logged_in": False, "message": "登录会话不存在或已过期，请重新发起登录"}

    resolved = resolve_cli_path(cli_path or session.get("cli_path"))
    if not resolved:
        return {"state": "failed", "logged_in": False, "message": "即梦画布 CLI 不存在，请重新安装"}

    code, out = _run([resolved, "auth", "account"], timeout=30)
    ok, data, error = _parse_envelope(out)
    if code == 0 and ok and data.get("userId"):
        return {
            "state": "success",
            "logged_in": True,
            "message": "登录成功",
            "account_info": data,
        }
    hint = ""
    if code != 0:
        hint = f"（auth account exit={code}: {out.strip()[:200]}）"
    elif error:
        hint = f"（{error.get('code')}: {error.get('message', '')[:160]}）"
    return {
        "state": "waiting",
        "logged_in": False,
        "message": f"尚未检测到登录完成，请在浏览器打开授权链接并完成授权{hint}",
    }


def clear_login_session() -> None:
    try:
        _redis().delete(_LOGIN_SESSION_KEY)
    except Exception:
        pass


# ---- Provider 连通性测试（worker 侧执行）----

def check_ready(cli_path: str | None = None) -> dict[str, Any]:
    """等价于 Provider.test_connection：auth account 成功即视为可用。"""
    resolved = resolve_cli_path(cli_path)
    if not resolved:
        legacy = find_legacy_cli()
        if legacy:
            return {
                "success": False,
                "message": "worker 节点仅检测到旧版即梦 CLI（dreamina），官方已替换为新版画布 CLI。"
                "请在「服务管理」页完成一键安装，或在 worker 所在机器执行 curl -fsSL "
                + INSTALL_SCRIPT_URL + " | bash",
            }
        return {
            "success": False,
            "message": "worker 节点未检测到即梦画布 CLI。请在「服务管理」页完成一键安装，"
            "或在 worker 所在机器执行 curl -fsSL " + INSTALL_SCRIPT_URL + " | bash",
        }
    code, out = _run([resolved, "auth", "account"], timeout=30)
    ok, data, error = _parse_envelope(out)
    if code == 0 and ok and data.get("userId"):
        return {"success": True, "message": "CLI 可用且登录态有效", "output": out.strip()[:_SNIPPET]}
    if error:
        return {
            "success": False,
            "message": f"CLI 已安装但自检失败（{error.get('code')}），通常表示未登录或登录态失效，请完成登录引导。"
            f"原始输出：{out.strip()[:200]}",
        }
    return {
        "success": False,
        "message": f"CLI 已安装但自检失败（exit={code}），通常表示未登录或登录态失效，请完成登录引导。"
        f"原始输出：{out.strip()[:200]}",
    }
