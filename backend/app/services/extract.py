"""抽取编排：图片 → 模型 → 解析 → 四道关 → 重试 → 置信度 → 缓存。

这个文件是整个 D2 的核心，也是答辩时"AI 技术深度"的主要证据。
它的设计原则只有一条：**宁可交给人，也不给一个看起来对的错答案。**
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.config import settings
from app.schemas import ExtractionResult, ExtractedFields, FieldConfidence, ImageMeta, ValidationReport
from app.services import validators
from app.services.image import PreparedImage, prepare_image, sha256_bytes
from app.services.llm import ProviderError, build_messages, get_provider, retry_messages


class ExtractionError(Exception):
    """抽取失败（JSON 解析不出来、模型不可用等）。"""


# 这几个字段决定结论能不能用，任何一个没把握，整体就不可信
CRITICAL_FIELDS = ["invoice_number", "invoice_date", "amount_incl_tax", "seller_name", "buyer_tax_id"]
FIELD_KEYS = [
    "invoice_code",
    "invoice_number",
    "invoice_date",
    "seller_name",
    "seller_tax_id",
    "buyer_name",
    "buyer_tax_id",
    "amount_excl_tax",
    "tax_amount",
    "amount_incl_tax",
    "tax_rate",
    "category",
]


# ------------------------------------------------------------------ 解析

def parse_json(text: str) -> dict[str, Any]:
    """模型很爱输出 ```json ... ``` 或者前面加一句"好的，这是结果"。这里都容错。"""
    raw = (text or "").strip()
    if not raw:
        raise ExtractionError("模型返回空内容")

    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ExtractionError(f"模型输出里找不到 JSON 对象：{text[:120]!r}")

    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"模型输出的 JSON 不合法：{exc.msg}") from exc

    if not isinstance(data, dict):
        raise ExtractionError("模型输出的顶层不是对象")
    return data


# ------------------------------------------------------------------ 置信度

def compute_confidence(data: dict[str, Any], report: dict[str, Any]) -> tuple[float, dict[str, float]]:
    """整体把握取"最没把握的关键字段"，而不是取平均。

    理由：报销审核是串联判断，五个字段里四个 0.99、一个 0.3，
    平均值看起来 0.85 挺好，但实际上这张票不该被信任。取最小值才诚实。
    """
    conf = data.get("confidence") or {}
    per_raw = conf.get("per_field") if isinstance(conf, dict) else None
    per: dict[str, float] = {}
    if isinstance(per_raw, dict):
        for key, value in per_raw.items():
            if isinstance(value, (int, float)) and 0 <= float(value) <= 1:
                per[str(key)] = float(value)

    for field in CRITICAL_FIELDS:
        empty = data.get(field) in (None, "", [])
        if empty:
            # 字段都没读到，把握就不可能高
            per[field] = min(per.get(field, 0.85), 0.30)
        else:
            per.setdefault(field, 0.85)

    overall = min(per[field] for field in CRITICAL_FIELDS)

    if data.get("is_invoice") is False:
        overall = min(overall, 0.20)
    if report["errors"]:
        overall = min(overall, 0.50)

    return round(max(0.0, min(overall, 1.0)), 2), {k: round(v, 2) for k, v in per.items()}


# ------------------------------------------------------------------ 归一化

def normalize_fields(data: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in FIELD_KEYS:
        value = data.get(key)
        if key.startswith("amount_") or key in ("tax_amount", "tax_rate"):
            fields[key] = validators.to_float(value)
        else:
            fields[key] = None if value in (None, "") else str(value).strip()

    rate = fields.get("tax_rate")
    if rate is not None and rate > 1:  # 模型有时给 6 而不是 0.06
        fields["tax_rate"] = round(rate / 100, 4)

    items: list[dict[str, Any]] = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        amount = validators.to_float(item.get("amount"))
        if name or amount is not None:
            items.append({"name": name or "未命名项目", "amount": amount or 0.0})
    fields["items"] = items
    return fields


# ------------------------------------------------------------------ 缓存

def _cache_path(sha: str):
    return settings.cache_dir / f"{sha}.json"


def cache_get(sha: str) -> dict[str, Any] | None:
    if not settings.cache_enabled:
        return None
    path = _cache_path(sha)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cache_put(sha: str, payload: dict[str, Any]) -> None:
    if not settings.cache_enabled:
        return
    try:
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_path(sha).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass  # 缓存失败不影响主流程


# ------------------------------------------------------------------ 主流程

async def extract_one(raw: bytes, *, owner: dict[str, Any] | None = None) -> ExtractionResult:
    """一张图 → 一个 ExtractionResult。

    owner 用来把"这张图已经存过"的信息带回去，方便 /files 接口回显原图。
    """
    started = time.perf_counter()
    sha = sha256_bytes(raw)

    cached = cache_get(sha)
    if cached:
        cached["cached"] = True
        cached["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return ExtractionResult(**cached)

    prepared: PreparedImage = prepare_image(raw, settings.image_max_edge)
    provider = get_provider(seed=sha)
    base_messages = build_messages(prepared.data_uri)

    messages = base_messages
    data: dict[str, Any] | None = None
    report: dict[str, Any] = {
        "schema_ok": False,
        "arithmetic_ok": True,
        "sanity_ok": True,
        "errors": ["尚未执行"],
        "warnings": [],
    }
    retry_count = 0
    last_error = ""

    for attempt in range(settings.max_retry + 1):
        try:
            chat = await provider.chat(messages)
        except ProviderError as exc:
            raise ExtractionError(str(exc)) from exc

        retry_count = attempt
        try:
            data = parse_json(chat.text)
            report = validators.validate(data)
            last_error = ""
        except ExtractionError as exc:
            data = None
            last_error = str(exc)
            report = {
                "schema_ok": False,
                "arithmetic_ok": True,
                "sanity_ok": True,
                "errors": [last_error],
                "warnings": [],
            }

        if not report["errors"]:
            break
        if attempt >= settings.max_retry:
            break
        messages = retry_messages(base_messages, chat.text, report["errors"])

    if data is None:
        raise ExtractionError(last_error or "模型未能输出可解析的结果")

    fields = normalize_fields(data)
    overall, per_field = compute_confidence(data, report)
    is_invoice = data.get("is_invoice") is not False

    if not is_invoice or report["errors"] or overall < settings.confidence_threshold:
        verdict_hint = "manual"
    else:
        verdict_hint = "pass"

    result = ExtractionResult(
        extraction_id=uuid.uuid4().hex[:12],
        is_invoice=is_invoice,
        fields=ExtractedFields(**fields),
        field_confidence=FieldConfidence(overall=overall, per_field=per_field),
        overall_confidence=overall,
        verdict_hint=verdict_hint,
        validation=ValidationReport(**report),
        provider=chat.provider,
        model=chat.model,
        cached=False,
        retry_count=retry_count,
        latency_ms=int((time.perf_counter() - started) * 1000),
        image=ImageMeta(
            sha256=sha,
            original_bytes=len(raw),
            compressed_bytes=prepared.compressed_bytes,
            width=prepared.width,
            height=prepared.height,
            mime=prepared.mime,
        ),
        raw_output=None,
    )

    cache_put(sha, result.model_dump())
    return result