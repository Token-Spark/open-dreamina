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
"""把任务用量换算成人民币估算值（纯标准库，CLI / MCP 共用）。

事实边界：
- 用量（quantity / unit）由后端从 Provider 回报中提取，见 backend/app/worker.py。
- 单价来自本地可编辑价目表 pricing.json，带 as_of 与 source，不联网、不猜价格。
- 换算结果一律是估算（estimate=true），不是账单；查不到规则时明确返回 null + reason。

价目表可用环境变量 OPEN_DREAMINA_PRICING_FILE 指向自定义文件覆盖。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_PRICING_PATH = Path(__file__).resolve().parent / "pricing.json"
ENV_PRICING_FILE = "OPEN_DREAMINA_PRICING_FILE"

# 计费单位枚举，与 backend/app/worker.py 的 BILLING_UNITS 保持一致。
BILLING_UNITS = ("token", "credit", "image", "video_second", "video")


class PricingError(RuntimeError):
    """价目表缺失或格式错误。"""


_CACHE: dict[str, Any] | None = None
_CACHE_PATH: str | None = None


def pricing_path() -> Path:
    raw = os.environ.get(ENV_PRICING_FILE)
    return Path(raw).expanduser() if raw else DEFAULT_PRICING_PATH


def load_pricing() -> dict[str, Any]:
    """读取价目表（按路径缓存，进程内环境变量变化也能生效）。"""
    global _CACHE, _CACHE_PATH
    path = pricing_path()
    key = str(path)
    if _CACHE is not None and _CACHE_PATH == key:
        return _CACHE
    if not path.is_file():
        raise PricingError(f"价目表不存在：{path}（可设置 {ENV_PRICING_FILE} 指定）")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PricingError(f"价目表读取/解析失败：{path}（{exc}）") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise PricingError(f"价目表格式错误：{path} 缺少 rules 数组")
    _CACHE, _CACHE_PATH = data, key
    return data


def _provider_matches(pattern: Any, provider: str | None) -> bool:
    """支持精确 slug、前缀通配（sparkhub-*）与全通配（*）。"""
    if not isinstance(pattern, str) or not pattern:
        return False
    if pattern == "*":
        return True
    if pattern.endswith("*"):
        return bool(provider) and provider.startswith(pattern[:-1])
    return pattern == provider


def _unit_matches(pattern: Any, unit: str | None) -> bool:
    if pattern is None or pattern == "*":
        return True
    return pattern == unit


def _specificity(item: dict[str, Any], model_id: str | None) -> tuple[int, int, int]:
    """匹配优先级：provider 越具体越好，其次 model，最后 unit 精确匹配。"""
    p = item.get("provider")
    provider_score = 0 if p == "*" else (1 if isinstance(p, str) and p.endswith("*") else 2)
    model_score = 2 if item.get("model") and item.get("model") == model_id else (0 if item.get("model") else 1)
    unit_score = 1 if item.get("unit") not in (None, "*") else 0
    return (provider_score, model_score, unit_score)


def _best_match(
    items: list[Any], provider: str | None, model_id: str | None, unit: str | None
) -> dict[str, Any] | None:
    candidates: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _provider_matches(item.get("provider"), provider):
            continue
        if item.get("model") and item["model"] != model_id:
            continue
        if not _unit_matches(item.get("unit"), unit):
            continue
        candidates.append((_specificity(item, model_id), item))
    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[0])[1]


def _fx_to_cny(pricing: dict[str, Any], currency: str | None) -> tuple[float | None, str | None, str | None]:
    """返回 (汇率, 汇率日期, 错误信息)。CNY 直接按 1.0 处理。"""
    cur = (currency or "CNY").upper()
    if cur == "CNY":
        return 1.0, None, None
    fx = pricing.get("fx") or {}
    entry = fx.get(f"{cur}_CNY") if isinstance(fx, dict) else None
    rate = entry.get("rate") if isinstance(entry, dict) else None
    if not isinstance(rate, (int, float)) or rate <= 0:
        return None, None, f"missing_fx_rate_{cur}_CNY"
    return float(rate), (entry.get("as_of") if isinstance(entry, dict) else None), None


def _empty_cost(reason: str, error: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "currency": "CNY",
        "estimated_cny": None,
        "estimate": True,
        "unit_price_cny": None,
        "pricing_as_of": None,
        "source": None,
        "accuracy": None,
        "fx_rate": None,
        "quantity_basis": None,
        "reason": reason,
        "reference": None,
        "disclaimer": None,
    }
    if error:
        out["error"] = error
    return out


def estimate_cost(
    *,
    provider: str | None,
    model_id: str | None,
    unit: str | None,
    quantity: float | None,
    quantity_basis: str | None = None,
) -> dict[str, Any]:
    """按用量与价目表估算人民币金额。任何异常都降级为 null + reason，绝不阻断任务报告。"""
    try:
        pricing = load_pricing()
    except PricingError as exc:
        return _empty_cost("pricing_table_unavailable", str(exc))

    base = _empty_cost("")
    base["pricing_as_of"] = pricing.get("as_of")
    base["disclaimer"] = pricing.get("disclaimer")
    base["quantity_basis"] = quantity_basis
    base["reason"] = None

    if quantity is None or not isinstance(quantity, (int, float)) or quantity < 0:
        base["reason"] = "usage_unavailable"
        return base
    if unit not in BILLING_UNITS:
        base["reason"] = "unknown_billing_unit"
        return base

    rules = pricing.get("rules") or []
    rule = _best_match(rules, provider, model_id, unit)
    if rule is None:
        unpriced = _best_match(pricing.get("unpriced") or [], provider, model_id, unit)
        base["reason"] = (unpriced or {}).get("reason") or "no_pricing_rule"
        if unpriced:
            base["reference"] = {
                "hint": unpriced.get("hint"),
                "official_reference": unpriced.get("official_reference"),
            }
        return base

    price = rule.get("unit_price")
    if not isinstance(price, (int, float)) or price < 0:
        base["reason"] = "invalid_unit_price"
        return base

    rate, fx_as_of, fx_error = _fx_to_cny(pricing, rule.get("price_currency"))
    if fx_error:
        base["reason"] = fx_error
        return base

    unit_price_cny = float(price) * (rate or 1.0)
    base.update(
        {
            "estimated_cny": round(float(quantity) * unit_price_cny, 4),
            "unit_price_cny": round(unit_price_cny, 8),
            "pricing_as_of": rule.get("as_of") or pricing.get("as_of"),
            "source": rule.get("source"),
            "accuracy": rule.get("accuracy"),
            "fx_rate": rate if (rule.get("price_currency") or "CNY").upper() != "CNY" else None,
            "reason": None,
        }
    )
    if fx_as_of:
        base["fx_as_of"] = fx_as_of
    return base


def describe_pricing() -> dict[str, Any]:
    """供 `opendreamina pricing` 打印当前生效价目表摘要，便于核对来源与日期。"""
    path = pricing_path()
    try:
        pricing = load_pricing()
    except PricingError as exc:
        return {"path": str(path), "loaded": False, "error": str(exc)}
    return {
        "path": str(path),
        "loaded": True,
        "currency": pricing.get("currency"),
        "as_of": pricing.get("as_of"),
        "disclaimer": pricing.get("disclaimer"),
        "fx": pricing.get("fx"),
        "rules": pricing.get("rules"),
        "unpriced": pricing.get("unpriced"),
    }
