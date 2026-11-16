"""公司配置：让"刚进来就因为抬头不符被驳回"这件事不可能发生。

一个部署服务一家公司：进站先把公司名、税号填上，R3 就按它比对；
提交期限和费用标准同理——R4/R5 读的是同一份档案，改完立刻生效，不用重启。

为什么不做成多租户：这一版的定位是"给一家公司做审核台"，
配置的是"这家公司是谁"，不是"同时服务几家公司"。多租户是另一件事（P1-8）。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from app.schemas import CompanySettings, CompanySettingsIn
from app.services import profile

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 中国纳税人识别号：15 / 17 / 18 / 20 位，统一按大写字母数字收
_TAX_ID = re.compile(r"^[0-9A-Z]{15,20}$")


@router.get("/company", response_model=CompanySettings, summary="当前公司配置")
def get_company() -> dict:
    return profile.get_with_meta()


@router.put("/company", response_model=CompanySettings, summary="保存公司配置（即时生效）")
def update_company(payload: CompanySettingsIn) -> dict:
    name = payload.name.strip()
    tax_id = payload.tax_id.strip().upper()

    if len(name) < 2:
        raise HTTPException(status_code=422, detail="公司名称至少 2 个字")
    if not _TAX_ID.match(tax_id):
        raise HTTPException(
            status_code=422,
            detail="纳税人识别号应为 15–20 位大写字母或数字（例如 91330100MA2A1B2C3D）",
        )
    for category, value in payload.limits.items():
        if category not in profile.LIMIT_CATEGORIES:
            raise HTTPException(status_code=422, detail=f"不认识的费用类目：{category}")
        if value < 0:
            raise HTTPException(status_code=422, detail=f"{category}标准不能为负数")

    return profile.save(
        {
            "name": name,
            "tax_id": tax_id,
            "deadline_days": payload.deadline_days,
            "limits": payload.limits,
        }
    )