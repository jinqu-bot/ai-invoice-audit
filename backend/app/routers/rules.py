"""规则清单接口。前端拿它渲染"我们怎么审的"一页，评委也能直接看到依据。"""

from fastapi import APIRouter

from app.schemas import RuleDef
from app.services import rules

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=list[RuleDef], summary="规则清单与依据")
def list_rules() -> list[dict]:
    return rules.rule_defs()