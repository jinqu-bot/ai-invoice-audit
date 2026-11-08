"""制度库接口：条款列表、检索、以及 D8 的问答。"""

from fastapi import APIRouter, HTTPException, Query

from app.mock import fixtures
from app.schemas import PolicyAnswer, PolicyDoc, PolicySearchResult
from app.services import policy, policy_qa

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("", response_model=list[PolicyDoc], summary="制度文档列表")
def list_docs() -> list[dict]:
    return fixtures.POLICY_DOCS


@router.get("/search", response_model=PolicySearchResult, summary="条款检索")
def search_policies(
    q: str = Query(min_length=1, description="自然语言问题，例如“住宿超标了怎么办”"),
    top_k: int = Query(default=3, ge=1, le=10),
) -> dict:
    """现在是关键词粗筛，只为让 B 先把"出处卡片"画出来。

    D8 换成混合检索 + 重排后，接口和返回字段完全不变。
    """
    return {"query": q, "clauses": policy.search(q, top_k)}


@router.get("/ask", response_model=PolicyAnswer, summary="制度问答（D8）")
def ask_policy(
    q: str = Query(min_length=2, max_length=200, description="例如：住宿费超标准了还能报吗"),
    top_k: int = Query(default=3, ge=1, le=6),
) -> dict:
    """按制度回答，**答不出来就说答不出来**。

    三个返回状态要分清（前端要据此换样式，别都当成"答好了"）：

    - `provider=openai-compat`：模型基于条款作答，`citations` 是依据
    - `provider=retrieval-only`：没接模型，只把条款原文摆出来
    - `provider=rules-only` + `refused=true`：制度里确实没相关条款，明确不答

    `grounded=false` 表示模型引用了检索结果里不存在的条号——这条回答不可信。
    """
    if not q.strip():
        raise HTTPException(status_code=422, detail="问题不能为空")
    return policy_qa.answer(q, top_k=top_k)
