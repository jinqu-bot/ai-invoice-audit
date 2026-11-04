"""制度库接口。D1 用内存假条款，D8 换成 Chroma 检索，路径和返回结构不变。"""

from fastapi import APIRouter, Query

from app.mock import fixtures
from app.schemas import PolicyDoc, PolicySearchResult

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("", response_model=list[PolicyDoc], summary="制度文档列表")
def list_docs() -> list[dict]:
    return fixtures.POLICY_DOCS


@router.get("/search", response_model=PolicySearchResult, summary="条款检索")
def search_policies(
    q: str = Query(min_length=1, description="自然语言问题，例如“住宿超标了怎么办”"),
    top_k: int = Query(default=3, ge=1, le=10),
) -> dict:
    """D1 是关键词粗筛，只为让 B 先把“出处卡片”画出来。

    D8 换成 混合检索 + 重排 后，接口和返回字段完全不变。
    """
    keywords = [k for k in q if k.strip()]
    scored = []
    for clause in fixtures.POLICY_CLAUSES:
        hit = sum(1 for kw in keywords if kw in clause["text"])
        scored.append((hit, clause))

    matched = [c for hit, c in scored if hit > 0] or [c for _, c in scored]
    matched.sort(key=lambda c: c["score"], reverse=True)
    return {"query": q, "clauses": matched[:top_k]}
