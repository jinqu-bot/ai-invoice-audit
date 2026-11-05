"""报销台账（内存版）。查重（R1）靠它。

D4 阶段没有数据库，用进程内字典。D5 换 SQLite 后只改这个文件的内部实现，
规则引擎和路由都不用动。

**预置的三条历史记录就是"重复票怎么造"的答案**（C 问过这个）：
想在演示里造一张重复票，把发票号码写成台账里已有的号即可，
不需要真的先提交一遍。台账里 66472890 这张，正好对应演示批次里那张红票
（INV-0005，已于 11-02 由张伟报销）。
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

_lock = threading.Lock()

# 发票号码 → 台账记录
_HISTORY: dict[str, dict[str, Any]] = {}

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
    },
]


def _seed_once() -> None:
    if _HISTORY:
        return
    for row in _SEED:
        _HISTORY[row["invoice_number"]] = dict(row)


_seed_once()


def find(invoice_number: str | None, invoice_code: str | None = None) -> dict[str, Any] | None:
    """按发票号码查历史。号码是发票的唯一标识，代码（票种批次）只做辅助核对。"""
    number = (invoice_number or "").strip()
    if not number:
        return None
    row = _HISTORY.get(number)
    if row is None:
        return None
    # 号码对上但代码对不上，多半是识别错位，仍然算命中——宁可让人确认，也不能放过
    return dict(row)


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
    with _lock:
        _HISTORY[number] = {
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


def size() -> int:
    return len(_HISTORY)


def reset() -> None:
    """测试用：把台账恢复成预置状态。"""
    with _lock:
        _HISTORY.clear()
        _seed_once()