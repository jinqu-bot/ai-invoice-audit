"""审核看板。

以前这里直接返回 fixtures 的假数据（128 张、18.6 万），而库里其实是 0 张——
两个页面各说各的，评委点一下就看穿了。

现在的规则：**优先读库里真审核过的票**；一张都没有时才退回演示样例，
并且把来源（`source`）一起返回，前端据此标注，不让假数据冒充真数据。
"""

from fastapi import APIRouter, Query

from app.mock import fixtures
from app.schemas import Dashboard
from app.services import store

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard, summary="看板数据（真实聚合，空库时退回演示样例）")
def get_dashboard(
    month: str = Query(default="2026-11", description="YYYY-MM"),
) -> dict:
    data = store.dashboard_month(month)
    if data.get("total_count"):
        return {**data, "source": "db"}
    # 空库：给演示样例，但必须带着 source=fixture 出去，前端会显式标注
    fallback = dict(fixtures.DASHBOARD)
    fallback["month"] = month
    fallback["source"] = "fixture"
    return fallback
