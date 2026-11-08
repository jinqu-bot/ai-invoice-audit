"""人工复核（D8）：驳回不是终点。

为什么要有这一层：前面 R0–R8 全部是机器判断，机器一定会判错——
抬头识别糊了、金额小数点错位、或者这张票确实特殊。

如果系统只有"驳回"没有"改判"，那它就是一台不讲理的机器：
用户拿着合规的票被拒，只能去吵，而系统里没有任何记录能证明谁对。
**改判必须留痕**：谁改的、改成什么、凭什么。这是制度能落地的底线，
也是答辩时"判错了怎么办"的唯一答案。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.services import db

# 人工能改成什么：就是机器那四种结论，不额外发明状态
ACTIONS = ("pass", "suspect", "reject", "manual")

_HEADLINE = {
    "pass": "人工复核通过",
    "suspect": "人工复核改为存疑",
    "reject": "人工复核维持驳回",
    "manual": "人工复核转人工处理",
}

_COLUMNS = (
    "review_id, invoice_id, decided_at, action, "
    "verdict_before, verdict_after, reviewer, reason, note"
)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def record(
    invoice_id: str,
    *,
    verdict_before: str,
    action: str,
    reviewer: str,
    reason: str,
    note: str = "",
) -> dict[str, Any]:
    """记一次复核。返回这条记录本身。"""
    review_id = f"RV-{uuid.uuid4().hex[:10]}"
    db.execute(
        f"INSERT INTO reviews ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            review_id,
            invoice_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            action,
            verdict_before,
            action,
            reviewer.strip() or "未登记",
            reason.strip(),
            (note or "").strip(),
        ),
    )
    row = db.one("SELECT * FROM reviews WHERE review_id = ?", (review_id,))
    return _row_to_dict(row) if row is not None else {}


def all_of(invoice_id: str) -> list[dict[str, Any]]:
    """这张票的完整复核轨迹，按时间正序——像聊天记录一样读。"""
    rows = db.query(
        "SELECT * FROM reviews WHERE invoice_id = ? ORDER BY decided_at ASC, rowid ASC",
        (invoice_id,),
    )
    return [_row_to_dict(row) for row in rows]


def latest_map(invoice_ids: list[str]) -> dict[str, dict[str, Any]]:
    """一批卡片一次查完，避免 N+1。返回 {invoice_id: 最后一次复核}。"""
    if not invoice_ids:
        return {}
    placeholders = ",".join("?" * len(invoice_ids))
    rows = db.query(
        f"SELECT * FROM reviews WHERE invoice_id IN ({placeholders}) "
        "ORDER BY decided_at ASC, rowid ASC",
        tuple(invoice_ids),
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest[row["invoice_id"]] = _row_to_dict(row)  # 后面的覆盖前面的
    return latest


def apply(card: dict[str, Any], review: dict[str, Any] | None) -> dict[str, Any]:
    """把复核结论盖到卡片上。没复核过就原样返回。"""
    if not review:
        return card
    patched = dict(card)
    after = review["verdict_after"]
    patched["verdict"] = after
    patched["headline"] = f"{_HEADLINE.get(after, '人工复核')}：{review['reason']}"
    patched["manual_review"] = after == "manual"
    patched["reviewed"] = True
    return patched


def apply_many(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = latest_map([card["invoice_id"] for card in cards])
    return [apply(card, latest.get(card["invoice_id"])) for card in cards]
