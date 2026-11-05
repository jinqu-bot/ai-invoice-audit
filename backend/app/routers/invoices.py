"""发票详情：字段、置信度、命中规则、制度引用、审核轨迹。"""

from fastapi import APIRouter, HTTPException

from app.mock import fixtures
from app.schemas import InvoiceDetail
from app.services import store

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


@router.get("/{invoice_id}", response_model=InvoiceDetail, summary="发票详情")
def get_invoice(invoice_id: str) -> dict:
    # 先查真实上传的批次，再退回演示数据
    detail = store.get_detail(invoice_id)
    if detail is not None:
        return detail

    detail = fixtures.get_detail(invoice_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"发票不存在：{invoice_id}")
    # 详情 = 卡片字段 + 明细字段，前端一次拿全，不用回列表再取
    return {**fixtures.card_of(detail), **detail}