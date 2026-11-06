"""报销台账（D5 起落库）。查重（R1）靠它。

以前是进程内字典，重启就没了——那么"重复报销"这条规则等于是摆设：
先传一张、重启后端、再传一张，就能重复报两次。
现在写进 SQLite，重启之后照样查得出来。

**预置的三条历史记录就是"重复票怎么造"的答案**：
把发票号码写成台账里已有的号即可。台账里 66472890 这张，
正好对应演示批次里那张红票（INV-0005，已于 11-02 由张伟报销）。
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


def _insert(row: dict[str, Any]) -> None:
    db.execute(
        f"INSERT OR REPLACE INTO reimbursements ({_columns}) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            row["invoice_number"],
            row.get("invoice_code"),
            row.get("seller_name"),
            row.get("amount_incl_tax"),
            row.get("invoice_date"),
            row.get("reimbursement_no"),
            row.get("employee"),
            row.get("dept"),
            row.get("submitted_at"),
            row.get("invoice_id"),
        ),
    )


def _ensure_seed() -> None:
    """台账为空时灌入预置记录。只在第一次真正用到时做，避免测试互相污染。"""
    row = db.one("SELECT COUNT(*) AS n FROM reimbursements")
    if row is not None and int(row["n"]) == 0:
        for item in _SEED:
            _insert(item)


def find(invoice_number: str | None, invoice_code: str | None = None) -> dict[str, Any] | None:
    """按发票号码查历史。号码是发票的唯一标识，代码（票种批次）只做辅助核对。"""
    number = (invoice_number or "").strip()
    if not number:
        return None
    _ensure_seed()
    row = db.one("SELECT * FROM reimbursements WHERE invoice_number = ?", (number,))
    return dict(row) if row is not None else None


def remember(
    fields: dict[str, Any],
    *,
    verdict: str,
    batch_id: str,
    invoice_id: str,
    employee: str = "报销人",
) -> None:
    """审核完记一笔，下次同样的票再进来就能查出来。

    只有 pass / suspect 入账：被驳回的票本来就该重开，转人工的还没定论。
    """
    number = (fields.get("invoice_number") or "").strip()
    if not number or verdict not in ("pass", "suspect"):
        return
    _insert(
        {
            "invoice_number": number,
            "invoice_code": fields.get("invoice_code") or "",
            "seller_name": fields.get("seller_name") or "",
            "amount_incl_tax": fields.get("amount_incl_tax") or 0.0,
            "invoice_date": fields.get("invoice_date") or "",
            "reimbursement_no": f"BX-{batch_id[-8:]}",
            "employee": employee,
            "dept": "—",
            "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "invoice_id": invoice_id,
        }
    )


def size() -> int:
    _ensure_seed()
    row = db.one("SELECT COUNT(*) AS n FROM reimbursements")
    return int(row["n"]) if row is not None else 0


def reset() -> None:
    """测试用：清空台账并恢复预置记录。"""
    db.execute("DELETE FROM reimbursements")
    _ensure_seed()