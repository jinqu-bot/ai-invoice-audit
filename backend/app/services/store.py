"""批次与发票存储（D5 起落库）。

一条发票的完整详情就是 `invoices.payload_json` 那一列：
卡片字段、识别字段、命中规则、引用、轨迹、建议全在里面。
DTO 形状对齐 schemas.py，读出来直接返回，不需要再拼一次。

图片落在磁盘（backend/data/uploads），库里只记路径和 mime——
把 5MB 的图塞进 SQLite 也能跑，但备份和排查会变难，不划算。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import ExtractionResult
from app.services import db, history
from app.services.rules import run_audit
from app.services.validators import REQUIRED_FIELDS

_lock = threading.Lock()


@dataclass
class StoredBatch:
    summary: dict[str, Any]
    cards: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)


# ------------------------------------------------------------------ 图片

def _upload_dir() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_image(raw: bytes, mime: str = "image/jpeg", filename: str | None = None) -> str:
    image_id = uuid.uuid4().hex[:16]
    suffix = {"image/png": ".png", "image/webp": ".webp", "image/bmp": ".bmp"}.get(mime, ".jpg")
    path = _upload_dir() / f"{image_id}{suffix}"
    path.write_bytes(raw)
    db.execute(
        "INSERT OR REPLACE INTO images (image_id, path, mime) VALUES (?,?,?)",
        (image_id, str(path), mime),
    )
    return image_id


def get_image(image_id: str) -> tuple[bytes, str] | None:
    row = db.one("SELECT path, mime FROM images WHERE image_id = ?", (image_id,))
    if row is None:
        return None
    path = Path(row["path"])
    if not path.exists():
        return None
    return path.read_bytes(), row["mime"]


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
    """当日序号自增。存在库里，重启后不会重号——内存计数器会。"""
    today = datetime.now().strftime("%Y%m%d")
    with _lock:
        row = db.one("SELECT seq FROM counters WHERE day = ?", (today,))
        seq = (int(row["seq"]) if row else 0) + 1
        db.execute(
            "INSERT INTO counters (day, seq) VALUES (?,?) "
            "ON CONFLICT(day) DO UPDATE SET seq = excluded.seq",
            (today, seq),
        )
    return f"B{today}-{seq:03d}"


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


def build_batch(
    batch_id: str,
    entries: list[tuple[str, str, ExtractionResult]],
    *,
    failures: list[dict[str, Any]] | None = None,
    elapsed_ms: int | None = None,
) -> StoredBatch:
    """entries: [(filename, image_id, extraction)] → 落库并返回可直接响应前端的批次。

    failures 是这一批里没能处理的文件（类型不对、识别失败……）。
    **一张失败不再让整批失败**，成功的照常入库，失败的原样告诉前端。
    """
    cards: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    failures = failures or []

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
            # D5 新增：原始文件名，前端可以显示"你传的是哪张"
            "filename": filename,
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

    if not cards:
        status = "failed" if failures else "done"
    elif failures:
        status = "partial"
    else:
        status = "done"

    providers = sorted({ext.provider for _, _, ext in entries})
    summary = {
        "batch_id": batch_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "invoice_count": len(cards),
        "status": status,
        "total_amount": round(sum(c["amount_incl_tax"] for c in cards), 2),
        "pass_count": sum(1 for c in cards if c["verdict"] == "pass"),
        "suspect_count": sum(1 for c in cards if c["verdict"] == "suspect"),
        "reject_count": sum(1 for c in cards if c["verdict"] == "reject"),
        "manual_count": sum(1 for c in cards if c["verdict"] == "manual"),
        "elapsed_ms": int(elapsed_ms if elapsed_ms is not None else sum(c["latency_ms"] for c in cards)),
        "failed_count": len(failures),
        # 一批里可能混着缓存命中和真实调用，来源不一致就如实写 mixed
        "provider": providers[0] if len(providers) == 1 else ("mixed" if providers else "fixture"),
    }

    _persist(summary, entries, details, failures)
    return StoredBatch(summary=summary, cards=cards, details=details, failures=failures)


def _persist(
    summary: dict[str, Any],
    entries: list[tuple[str, str, ExtractionResult]],
    details: dict[str, dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    names = {invoice_id: entry[0] for invoice_id, entry in zip(details, entries)}
    db.execute(
        "INSERT OR REPLACE INTO batches (batch_id, created_at, status, provider, invoice_count,"
        " total_amount, pass_count, suspect_count, reject_count, manual_count, elapsed_ms,"
        " failures_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            summary["batch_id"], summary["created_at"], summary["status"], summary["provider"],
            summary["invoice_count"], summary["total_amount"], summary["pass_count"],
            summary["suspect_count"], summary["reject_count"], summary["manual_count"],
            summary["elapsed_ms"], db.dumps(failures),
        ),
    )
    for invoice_id, payload in details.items():
        db.execute(
            "INSERT OR REPLACE INTO invoices (invoice_id, batch_id, seq, filename, verdict,"
            " headline, confidence, amount_incl_tax, invoice_number, invoice_date, seller_name,"
            " category, payload_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                invoice_id,
                payload["batch_id"],
                payload["seq"],
                names.get(invoice_id),
                payload["verdict"],
                payload["headline"],
                payload["confidence"],
                payload["amount_incl_tax"],
                payload["invoice_number"],
                payload["invoice_date"],
                payload["seller_name"],
                payload["category"],
                db.dumps(payload),
            ),
        )


# ------------------------------------------------------------------ 读取

def _summary_of(row: Any) -> dict[str, Any]:
    failures = db.loads(row["failures_json"], [])
    return {
        "batch_id": row["batch_id"],
        "created_at": row["created_at"],
        "invoice_count": row["invoice_count"],
        "status": row["status"],
        "total_amount": row["total_amount"],
        "pass_count": row["pass_count"],
        "suspect_count": row["suspect_count"],
        "reject_count": row["reject_count"],
        "manual_count": row["manual_count"],
        "elapsed_ms": row["elapsed_ms"],
        "failed_count": len(failures),
        "provider": row["provider"],
    }


def get_batch(batch_id: str) -> StoredBatch | None:
    row = db.one("SELECT * FROM batches WHERE batch_id = ?", (batch_id,))
    if row is None:
        return None

    cards: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    for inv in db.query(
        "SELECT payload_json FROM invoices WHERE batch_id = ? ORDER BY seq", (batch_id,)
    ):
        payload = db.loads(inv["payload_json"], {})
        if not payload:
            continue
        details[payload["invoice_id"]] = payload
        cards.append({key: payload[key] for key in payload if key not in (
            "fields", "field_confidence", "hit_rules", "citations", "trace",
            "suggestions", "missing_fields",
        )})

    return StoredBatch(
        summary=_summary_of(row),
        cards=cards,
        details=details,
        failures=db.loads(row["failures_json"], []),
    )


def list_batches(limit: int | None = None, offset: int = 0) -> tuple[int, list[dict[str, Any]]]:
    """返回 (总数, 当前页)。按创建时间倒序，同时间按批次号倒序保证稳定。"""
    total_row = db.one("SELECT COUNT(*) AS n FROM batches")
    total = int(total_row["n"]) if total_row else 0
    sql = "SELECT * FROM batches ORDER BY created_at DESC, batch_id DESC"
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (limit, max(0, offset))
    rows = db.query(sql, params)
    return total, [_summary_of(row) for row in rows]


def get_detail(invoice_id: str) -> dict[str, Any] | None:
    row = db.one("SELECT payload_json FROM invoices WHERE invoice_id = ?", (invoice_id,))
    if row is None:
        return None
    payload = db.loads(row["payload_json"], None)
    return payload or None


def get_failures(batch_id: str) -> list[dict[str, Any]]:
    row = db.one("SELECT failures_json FROM batches WHERE batch_id = ?", (batch_id,))
    if row is None:
        return []
    return db.loads(row["failures_json"], [])


def reset() -> None:
    """测试用：清空所有批次、发票、图片。台账在 history 里单独 reset。"""
    db.execute("DELETE FROM invoices")
    db.execute("DELETE FROM batches")
    db.execute("DELETE FROM images")
    db.execute("DELETE FROM counters")
    upload_dir = Path(settings.upload_dir)
    if upload_dir.exists():
        for item in upload_dir.glob("*"):
            try:
                item.unlink()
            except OSError:
                pass