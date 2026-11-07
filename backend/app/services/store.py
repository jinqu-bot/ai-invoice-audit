"""批次与发票存储（D5 落库，D6 支持"边跑边存"）。

D6 之后一个批次的生命周期是三段，对应三个函数：
`create_batch()` → 若干次 `add_invoice()` → `finish_batch()`。
这样批次在 `processing` 期间就能被 `/results` 和 `/stream` 看到，
而不是等全部跑完才凭空出现。

一张发票的完整详情就是 `invoices.payload_json` 那一列：
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

# 详情里属于"卡片"的键。存进 payload 一份就够，读的时候按这个集合切。
_CARD_KEYS = (
    "invoice_id", "batch_id", "seq", "image_url", "verdict", "headline",
    "seller_name", "invoice_number", "invoice_date", "amount_incl_tax",
    "category", "confidence", "manual_review", "hit_rule_codes", "latency_ms",
    "filename", "provider", "model",
)


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


# ------------------------------------------------------------------ 三段式写入

def create_batch(
    batch_id: str, *, expected: int = 0, failures: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """先落一个 `processing` 的壳，让页面立刻能打开它。

    `expected` 是**待审张数**，必须以它的形式写进 `invoice_count`：
    页面要靠这个数字立刻摆出 N 个骨架屏。等收口时再改成实际张数
    （有文件失败的话会变少）。
    """
    failures = failures or []
    summary = {
        "batch_id": batch_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "invoice_count": expected,
        "status": "processing",
        "total_amount": 0.0,
        "pass_count": 0,
        "suspect_count": 0,
        "reject_count": 0,
        "manual_count": 0,
        "elapsed_ms": 0,
        "failed_count": len(failures),
        "provider": "fixture",
    }
    db.execute(
        "INSERT OR REPLACE INTO batches (batch_id, created_at, status, provider, invoice_count,"
        " total_amount, pass_count, suspect_count, reject_count, manual_count, elapsed_ms,"
        " failures_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            summary["batch_id"], summary["created_at"], summary["status"], summary["provider"],
            expected, 0.0, 0, 0, 0, 0, 0, db.dumps(failures),
        ),
    )
    return summary


def add_invoice(
    batch_id: str,
    *,
    seq: int,
    filename: str,
    image_id: str,
    ext: ExtractionResult,
) -> dict[str, Any]:
    """审一张、存一张、入一次台账。返回 {card, detail}，可直接推给前端。"""
    invoice_id = f"INV-{batch_id}-{seq:02d}"
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
        "seq": seq,
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
        "filename": filename,
        # 这张卡的数字是谁给的：真模型还是演示模型。前端必须据此标注，
        # 不然"演示数据"会被当成"读出来的票面"。
        "provider": ext.provider,
        "model": ext.model,
    }

    suggestions = _extract_suggestions(ext)
    for tip in audit.suggestions:
        if tip not in suggestions:
            suggestions.append(tip)

    detail = {
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

    db.execute(
        "INSERT OR REPLACE INTO invoices (invoice_id, batch_id, seq, filename, verdict,"
        " headline, confidence, amount_incl_tax, invoice_number, invoice_date, seller_name,"
        " category, payload_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            invoice_id, batch_id, seq, filename, card["verdict"], card["headline"],
            card["confidence"], card["amount_incl_tax"], card["invoice_number"],
            card["invoice_date"], card["seller_name"], card["category"], db.dumps(detail),
        ),
    )

    # 审完入台账：下次同样的票再进来才查得出来。
    # 放在这里而不是路由里，是为了让同一批里重复上传的两张也能互相查出来。
    history.remember(
        fields.model_dump(),
        verdict=audit.verdict,
        batch_id=batch_id,
        invoice_id=invoice_id,
        source=ext.provider,
    )

    return {"card": card, "detail": detail}


def finish_batch(
    batch_id: str,
    *,
    elapsed_ms: int | None = None,
    failures: list[dict[str, Any]] | None = None,
    providers: set[str] | None = None,
) -> dict[str, Any]:
    """收口：从库里重算汇总，写状态。

    汇总数字从 `invoices` 表现算，而不是一路累加——累加一旦漏一次就永久错，
    重算每次都是对的，代价只是一次小查询。
    """
    failures = failures if failures is not None else get_failures(batch_id)
    rows = db.query(
        "SELECT verdict, amount_incl_tax FROM invoices WHERE batch_id = ?", (batch_id,)
    )
    count = len(rows)
    if count == 0:
        status = "failed" if failures else "done"
    elif failures:
        status = "partial"
    else:
        status = "done"

    row = db.one("SELECT created_at FROM batches WHERE batch_id = ?", (batch_id,))
    provider = "fixture"
    if providers:
        provider = next(iter(providers)) if len(providers) == 1 else "mixed"

    summary = {
        "batch_id": batch_id,
        "created_at": row["created_at"] if row else datetime.now().strftime("%Y-%m-%d %H:%M"),
        "invoice_count": count,
        "status": status,
        "total_amount": round(sum(float(r["amount_incl_tax"] or 0) for r in rows), 2),
        "pass_count": sum(1 for r in rows if r["verdict"] == "pass"),
        "suspect_count": sum(1 for r in rows if r["verdict"] == "suspect"),
        "reject_count": sum(1 for r in rows if r["verdict"] == "reject"),
        "manual_count": sum(1 for r in rows if r["verdict"] == "manual"),
        "elapsed_ms": int(elapsed_ms or 0),
        "failed_count": len(failures),
        "provider": provider,
    }
    db.execute(
        "UPDATE batches SET status = ?, invoice_count = ?, total_amount = ?, pass_count = ?,"
        " suspect_count = ?, reject_count = ?, manual_count = ?, elapsed_ms = ?,"
        " failures_json = ?, provider = ? WHERE batch_id = ?",
        (
            status, count, summary["total_amount"], summary["pass_count"],
            summary["suspect_count"], summary["reject_count"], summary["manual_count"],
            summary["elapsed_ms"], db.dumps(failures), provider, batch_id,
        ),
    )
    return summary


def build_batch(
    batch_id: str,
    entries: list[tuple[str, str, ExtractionResult]],
    *,
    failures: list[dict[str, Any]] | None = None,
    elapsed_ms: int | None = None,
) -> StoredBatch:
    """一次跑完的便捷入口（测试、脚本用）。线上走 create/add/finish 三段。"""
    create_batch(batch_id, expected=len(entries), failures=failures)
    for index, (filename, image_id, ext) in enumerate(entries, start=1):
        add_invoice(batch_id, seq=index, filename=filename, image_id=image_id, ext=ext)
    elapsed = elapsed_ms if elapsed_ms is not None else sum(ext.latency_ms for _, _, ext in entries)
    finish_batch(
        batch_id,
        elapsed_ms=int(elapsed),
        failures=failures,
        providers={ext.provider for _, _, ext in entries},
    )
    stored = get_batch(batch_id)
    assert stored is not None
    return stored


# ------------------------------------------------------------------ 读取

def _cards_of(batch_id: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cards: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    for inv in db.query(
        "SELECT payload_json FROM invoices WHERE batch_id = ? ORDER BY seq", (batch_id,)
    ):
        payload = db.loads(inv["payload_json"], {})
        if not payload:
            continue
        details[payload["invoice_id"]] = payload
        cards.append({key: payload[key] for key in _CARD_KEYS if key in payload})
    return cards, details


def _summary_of(row: Any, cards: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    failures = db.loads(row["failures_json"], [])
    summary = {
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
    # processing 期间库里的计数还是 0，用已落库的卡片现算，
    # 否则页面会显示"共 0 张"却有 3 张卡。
    if cards is not None:
        # 取较大者：create 时是待审张数（页面据此摆骨架屏），
        # 收口时是实际张数。两种情况都不会说谎。
        summary["invoice_count"] = max(int(summary["invoice_count"] or 0), len(cards))
        summary["total_amount"] = round(sum(float(c["amount_incl_tax"] or 0) for c in cards), 2)
        for verdict, key in (
            ("pass", "pass_count"),
            ("suspect", "suspect_count"),
            ("reject", "reject_count"),
            ("manual", "manual_count"),
        ):
            summary[key] = sum(1 for c in cards if c["verdict"] == verdict)
    return summary


def get_batch(batch_id: str) -> StoredBatch | None:
    row = db.one("SELECT * FROM batches WHERE batch_id = ?", (batch_id,))
    if row is None:
        return None
    cards, details = _cards_of(batch_id)
    return StoredBatch(
        summary=_summary_of(row, cards),
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


def recover_interrupted() -> int:
    """把停在上次的 `processing` 批次标成失败。

    后台任务活在进程内存里，重启就没了。不处理的话这些批次会永远转圈，
    页面看起来像卡死——写明"服务重启，本批中断"比装死强。
    """
    rows = db.query("SELECT batch_id, failures_json FROM batches WHERE status = 'processing'")
    for row in rows:
        failures = db.loads(row["failures_json"], [])
        failures.append(
            {
                "filename": "—",
                "code": "INTERRUPTED",
                "message": "服务重启，本批中断；已完成的发票仍可查看",
            }
        )
        db.execute(
            "UPDATE batches SET status = 'failed', failures_json = ? WHERE batch_id = ?",
            (db.dumps(failures), row["batch_id"]),
        )
    return len(rows)


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