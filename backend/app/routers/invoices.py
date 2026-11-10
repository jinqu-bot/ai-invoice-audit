"""发票详情 + 人工复核（D8）。

复核接口是这套系统的"最后一公里"：前 8 条规则定的是机器怎么看，
这个接口定的是**机器看错时，人的判断怎么覆盖它，以及这次覆盖留下了什么痕迹**。
"""

from fastapi import APIRouter, HTTPException

from app.mock import fixtures
from app.schemas import InvoiceDetail, ReviewIn, ReviewRecord
from app.services import reviews, rules, store

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def _base_detail(invoice_id: str) -> dict | None:
    """真实批次优先，其次演示数据。两条来源都要能复核，否则演示时讲不通。"""
    detail = store.get_detail(invoice_id)
    if detail is None:
        demo = fixtures.get_detail(invoice_id)
        if demo is None:
            return None
        detail = {**fixtures.card_of(demo), **demo}

    # 演示数据和 D7 之前的历史记录里，命中是手写的、没有依据条款。
    # 在这一层补齐，界面才不会出现"有的规则指得出第几条、有的指不出"。
    detail = {**detail, "hit_rules": rules.attach_basis(detail.get("hit_rules") or [])}
    return detail


def _with_reviews(invoice_id: str, detail: dict) -> dict:
    records = reviews.all_of(invoice_id)
    latest = records[-1] if records else None
    merged = reviews.apply(detail, latest)
    merged["reviews"] = records
    return merged


@router.get("/{invoice_id}", response_model=InvoiceDetail, summary="发票详情")
def get_invoice(invoice_id: str) -> dict:
    detail = _base_detail(invoice_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"发票不存在：{invoice_id}")
    return _with_reviews(invoice_id, detail)


@router.post(
    "/{invoice_id}/review",
    response_model=InvoiceDetail,
    summary="人工复核改判（D8）",
)
def review_invoice(invoice_id: str, payload: ReviewIn) -> dict:
    """把这张票改判成人给出的结论，并留下一条不可删的轨迹。

    规则上的三条底线：
    - **理由必填**：没有理由的改判等于没留痕，Pydantic 这一层就挡住了；
    - **不能改判成不存在的东西**：结论只能是 pass / suspect / reject / manual；
    - **原结论一并记下**：只写"现在是 pass"没用，得知道"之前机器说是 reject"。
    """
    detail = _base_detail(invoice_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"发票不存在：{invoice_id}")

    records = reviews.all_of(invoice_id)
    before = reviews.apply(detail, records[-1] if records else None)["verdict"]

    reviews.record(
        invoice_id,
        verdict_before=before,
        action=payload.action,
        reviewer=payload.reviewer,
        reason=payload.reason,
        note=payload.note,
    )
    return _with_reviews(invoice_id, detail)
