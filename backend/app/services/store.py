"""批次存储 + 卡片组装。

D2 起这里做的是：抽取结果 → 跑规则引擎 → 组装成前端直接能渲染的卡片和详情。
D4 起 verdict 是规则算出来的，不再是识别质量的复读。

还没有数据库，用进程内字典就够了。D5 换 SQLite，只要函数签名不变，路由一行都不用改。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.config import settings
from app.schemas import ExtractionResult, InvoiceDetail
from app.services import history
from app.services.rules import run_audit
from app.services.validators import REQUIRED_FIELDS

_lock = threading.Lock()


@dataclass
class StoredBatch:
    summary: dict[str, Any]
    cards: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, dict[str, Any]] = field(default_factory=dict)


_BATCHES: dict[str, StoredBatch] = {}
_IMAGES: dict[str, tuple[bytes, str]] = {}
_DAY_SEQ: dict[str, int] = {}


# ------------------------------------------------------------------ 图片

def save_image(raw: bytes, mime: str = "image/jpeg") -> str:
    image_id = uuid.uuid4().hex[:16]
    with _lock:
        _IMAGES[image_id] = (raw, mime)
    return image_id


def get_image(image_id: str) -> tuple[bytes, str] | None:
    return _IMAGES.get(image_id)


def guess_mime(filename: str) -> str:
    lower = (filename or "").lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".bmp"):
        return "image/bmp"
    return "image/jpeg"


# ------------------------------------------------------------------ 批次号

def next_batch_id() -> str:
    today = datetime.now().strftime("%Y%m%d")
    with _lock:
        _DAY_SEQ[today] = _DAY_SEQ.get(today, 0) + 1
        return f"B{today}-{_DAY_SEQ[today]:03d}"


# ------------------------------------------------------------------ 组装

def _missing_fields(ext: ExtractionResult) -> list[str]:
    """哪些关键字段根本没识别出来。

    detail 里这些格子会填 0 或空串，否则前端到处判空。代价是"没识别到"和
    "确实是 0"长得一样，所以必须单独把这个名单给出去，人工复核才不会把
    0.00 当成真实金额。
    """
    data = ext.fields.model_dump()
    missing: list[str] = []
    for name in REQUIRED_FIELDS:
        value = data.get(name)
        if value is None or value == "" or value == 0:
            missing.append(name)
    return missing


def _extract_trace(ext: ExtractionResult) -> list[dict[str, Any]]:
    """抽取这一趟做了什么。

    只到"抄下来 + 校验"为止；置信度闸门和业务规则归规则引擎，从第 3 步接上，
    免得同一个动作在时间线上出现两次。
    """
    fields = ext.fields
    return [
        {
            "step": 1,
            "tool": "extract_fields",
            "title": "要素抽取",
            "reason": (
                "先把票面上的东西原样抄下来。后面所有判断都建立在它上面，"
                "所以这一步宁可标低把握，也不猜。"
            ),
            "status": "ok" if ext.is_invoice else "error",
            "latency_ms": max(1, ext.latency_ms // 2),
            "args": {"provider": ext.provider, "model": ext.model},
            "result": {
                "is_invoice": ext.is_invoice,
                "invoice_number": fields.invoice_number,
                "amount_incl_tax": fields.amount_incl_tax,
                "retry_count": ext.retry_count,
            },
        },
        {
            "step": 2,
            "tool": "validate_fields",
            "title": "四道关校验",
            "reason": (
                "模型抄错一个数字，后面所有结论都是错的。"
                "所以先用算术勾稽和常识把明显不对的挡下来。"
            ),
            "status": "ok" if not ext.validation.errors else "error",
            "latency_ms": 3,
            "args": {"checks": ["格式", "金额勾稽", "日期与税号常识"]},
            "result": {
                "errors": ext.validation.errors,
                "warnings": ext.validation.warnings,
            },
        },
    ]


def _extract_suggestions(ext: ExtractionResult) -> list[str]:
    """识别层面的改进建议，和规则命中给的建议不是一回事。"""
    tips: list[str] = []
    if not ext.is_invoice:
        return ["确认上传的是发票照片，而不是订单截图或聊天记录", "重新上传票面完整的照片"]
    if ext.overall_confidence < settings.confidence_threshold:
        tips.append("重拍一张：平铺、不折叠、光线均匀、四角都在画面内")
        tips.append("或者手动补录发票号码与价税合计")
    if ext.validation.errors:
        tips.append("对照原图核对金额是否抄错")
    tips.extend(ext.validation.warnings)
    return tips


def build_batch(batch_id: str, entries: list[tuple[str, str, ExtractionResult]]) -> StoredBatch:
    """entries: [(filename, image_id, extraction)] → 可直接返回给前端的批次。"""
    cards: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}

    for index, (filename, image_id, ext) in enumerate(entries, start=1):
        invoice_id = f"INV-{batch_id}-{index:02d}"
        fields = ext.fields
        category = fields.category if fields.category in (
            "住宿", "餐饮", "交通", "办公", "招待", "其他"
        ) else "其他"

        extract_trace = _extract_trace(ext)
        audit = run_audit(
            fields,
            confidence=ext.overall_confidence,
            is_invoice=ext.is_invoice,
            history=history,
            validation_errors=ext.validation.errors,
            start_step=len(extract_trace) + 1,
        )

        card = {
            "invoice_id": invoice_id,
            "batch_id": batch_id,
            "seq": index,
            "image_url": f"/api/files/{image_id}.jpg",
            "verdict": audit.verdict,
            "headline": audit.headline,
            "seller_name": fields.seller_name or "未识别",
            "invoice_number": fields.invoice_number or "—",
            "invoice_date": fields.invoice_date or "—",
            "amount_incl_tax": fields.amount_incl_tax or 0.0,
            "category": category,
            "confidence": ext.overall_confidence,
            "manual_review": audit.verdict == "manual",
            "hit_rule_codes": [hit["code"] for hit in audit.hits],
            "latency_ms": ext.latency_ms,
        }
        cards.append(card)

        suggestions = _extract_suggestions(ext)
        for tip in audit.suggestions:
            if tip not in suggestions:
                suggestions.append(tip)

        details[invoice_id] = {
            **card,
            "fields": {
                "invoice_code": fields.invoice_code or "",
                "invoice_number": fields.invoice_number or "",
                "invoice_date": fields.invoice_date or "",
                "seller_name": fields.seller_name or "",
                "seller_tax_id": fields.seller_tax_id or "",
                "buyer_name": fields.buyer_name or "",
                "buyer_tax_id": fields.buyer_tax_id or "",
                "amount_excl_tax": fields.amount_excl_tax or 0.0,
                "tax_amount": fields.tax_amount or 0.0,
                "amount_incl_tax": fields.amount_incl_tax or 0.0,
                "tax_rate": fields.tax_rate or 0.0,
                "category": category,
                "items": [item.model_dump() for item in fields.items],
            },
            "field_confidence": ext.field_confidence.model_dump(),
            "hit_rules": audit.hits,
            "citations": audit.citations,
            "trace": extract_trace + audit.trace,
            "suggestions": suggestions,
            "missing_fields": _missing_fields(ext),
        }

        # 审完入台账：下次同样的票再进来才查得出来。
        # 放在这里而不是路由里，是为了让同一批里重复上传的两张也能互相查出来。
        history.remember(
            fields.model_dump(),
            verdict=audit.verdict,
            batch_id=batch_id,
            invoice_id=invoice_id,
        )

    total = round(sum(c["amount_incl_tax"] for c in cards), 2)
    providers = sorted({ext.provider for _, _, ext in entries})
    summary = {
        "batch_id": batch_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "invoice_count": len(cards),
        "status": "done",
        "total_amount": total,
        "pass_count": sum(1 for c in cards if c["verdict"] == "pass"),
        "suspect_count": sum(1 for c in cards if c["verdict"] == "suspect"),
        "reject_count": sum(1 for c in cards if c["verdict"] == "reject"),
        "manual_count": sum(1 for c in cards if c["verdict"] == "manual"),
        "elapsed_ms": sum(c["latency_ms"] for c in cards),
        # 一批里可能混着缓存命中和真实调用，来源不一致就如实写 mixed
        "provider": providers[0] if len(providers) == 1 else ("mixed" if providers else "fixture"),
    }

    batch = StoredBatch(summary=summary, cards=cards, details=details)
    with _lock:
        _BATCHES[batch_id] = batch
    return batch


# ------------------------------------------------------------------ 读取

def get_batch(batch_id: str) -> StoredBatch | None:
    return _BATCHES.get(batch_id)


def list_batches() -> list[dict[str, Any]]:
    items = [b.summary for b in _BATCHES.values()]
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items


def get_detail(invoice_id: str) -> dict[str, Any] | None:
    for batch in _BATCHES.values():
        if invoice_id in batch.details:
            return batch.details[invoice_id]
    return None


def reset() -> None:
    """测试用：清空批次与图片。台账在 history 里单独 reset。"""
    with _lock:
        _BATCHES.clear()
        _IMAGES.clear()