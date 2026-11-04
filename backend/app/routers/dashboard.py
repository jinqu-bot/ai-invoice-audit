"""审核看板数据（D1 是聚合假数据）。"""

from fastapi import APIRouter, Query

from app.mock import fixtures
from app.schemas import Dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard, summary="看板数据")
def get_dashboard(
    month: str = Query(default="2026-11", description="YYYY-MM"),
) -> dict:
    data = dict(fixtures.DASHBOARD)
    data["month"] = month
    return data
