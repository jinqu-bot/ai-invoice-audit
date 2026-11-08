"""按识别来源隔离的审核记录；这些记录不是实际报销完成凭证。

fixture/mock-vlm 仅供演示；openai-compat 仅查模型来源记录。
旧 reimbursements 表保留原样，可验证来源的记录按来源复制，其他记录隔离。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services import db

_SEED: list[dict[str, Any]] = [
    {
        "invoice_number": "66472890",
        "invoice_code": "033002200115",
        "seller_name": "杭州老码头餐饮管理有限公司",
        "amount_incl_tax": 486.0,
        "invoice_date": "2026-10-28",
        "reimbursement_no": "BX-1102-007",
        "employee": "张伟",
        "dept": "销售部",
        "submitted_at": "2026-11-02 15:21",
        "invoice_id": None,
    },
    {
        "invoice_number": "51022773",
        "invoice_code": "033002200121",
        "seller_name": "上海如家酒店管理有限公司",
        "amount_incl_tax": 736.0,
        "invoice_date": "2026-10-18",
        "reimbursement_no": "BX-1019-002",
        "employee": "李娜",
        "dept": "市场部",
        "submitted_at": "2026-10-19 09:48",
        "invoice_id": None,
    },
    {
        "invoice_number": "62918405",
        "invoice_code": "033002200122",
        "seller_name": "北京首都航空有限公司",
        "amount_incl_tax": 1240.0,
        "invoice_date": "2026-09-30",
        "reimbursement_no": "BX-1008-011",
        "employee": "王强",
        "dept": "研发部",
        "submitted_at": "2026-10-08 17:05",
        "invoice_id": None,
    },
]

_columns = (
    "invoice_number, invoice_code, seller_name, amount_incl_tax, invoice_date, "
    "reimbursement_no, employee, dept, submitted_at, invoice_id"
)


def _insert(row: dict[str, Any], source: str, *, preserve: bool = False) -> None:
    mode = "IGNORE" if preserve else "REPLACE"
    db.execute(
        f"INSERT OR {mode} INTO audit_history (source, {_columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (source, *(row.get(key.strip()) for key in _columns.split(","))),
    )


def _ensure_seed() -> None:
    # 旧表保留原样作审计备份。只有能关联到明确来源的记录才进入对应分区；
    # 无来源、混合来源不参与查重，避免把污染记录当成真实报销凭证。
    for row in db.query("SELECT r.*, b.provider FROM reimbursements r LEFT JOIN invoices i "
                        "ON i.invoice_id=r.invoice_id LEFT JOIN batches b ON b.batch_id=i.batch_id"):
        item = dict(row)
        source = item.pop("provider")
        if source not in ("mock-vlm", "openai-compat", "fixture"):
            source = "legacy-unknown"
        if item.get("employee") in (None, "", "报销人", "他人"):
            item["employee"] = "未登记"
        _insert(item, source, preserve=True)
    for item in _SEED:
        _insert(item, "fixture", preserve=True)


def find(invoice_number: str | None, invoice_code: str | None = None,
         *, source: str = "mock-vlm") -> dict[str, Any] | None:
    number = (invoice_number or "").strip()
    if not number or source not in ("mock-vlm", "fixture", "openai-compat"):
        return None
    _ensure_seed()
    # 演示允许命中预置样例；模型记录永远看不到演示/未知来源的号码。
    sources = (source, "fixture") if source == "mock-vlm" else (source, source)
    row = db.one("SELECT * FROM audit_history WHERE invoice_number=? AND source IN (?,?) "
                 "ORDER BY CASE WHEN source=? THEN 0 ELSE 1 END LIMIT 1", (number, *sources, source))
    return dict(row) if row is not None else None


class _ScopedHistory:
    def __init__(self, source: str):
        self.source = source

    def find(self, number: str | None, code: str | None = None) -> dict[str, Any] | None:
        return find(number, code, source=self.source)


def for_provider(source: str) -> _ScopedHistory:
    return _ScopedHistory(source)


def remember(fields: dict[str, Any], *, verdict: str, batch_id: str,
             invoice_id: str, employee: str = "未登记", source: str = "mock-vlm") -> None:
    """保存审核记录，不代表已经完成真实报销。按识别来源分区查重。"""
    number = (fields.get("invoice_number") or "").strip()
    if not number or verdict not in ("pass", "suspect"):
        return
    if source not in ("mock-vlm", "fixture", "openai-compat"):
        source = "legacy-unknown"
    _insert({**fields, "invoice_number": number,
             "reimbursement_no": f"BX-{batch_id[-8:]}",
             "employee": employee if employee not in ("", "报销人", "他人") else "未登记",
             "dept": "—", "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
             "invoice_id": invoice_id}, source)


def size() -> int:
    _ensure_seed()
    row = db.one("SELECT COUNT(*) AS n FROM audit_history")
    return int(row["n"]) if row else 0


def reset() -> None:
    """仅用于临时测试库，不用于清理生产数据。"""
    db.execute("DELETE FROM reimbursements")
    db.execute("DELETE FROM audit_history")
    _ensure_seed()
