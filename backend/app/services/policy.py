"""制度条款库——规则引擎的"依据"从这里取。

现在是一份手写语料，按 (doc_id, 条号) 取用。D8 换成向量检索后，
只要 cite() / search() 的签名不变，规则引擎一行都不用改。

为什么规则要单独从条款取文本，而不是在代码里写死一句话：
"住宿超 800" 是能算的，"依据差旅费管理办法第 12 条" 是能查的。
前者机器会做，后者评委要看——两个都不能少。
"""

from __future__ import annotations

from typing import Any

from app.mock import fixtures

_BY_KEY: dict[tuple[str, str], dict[str, Any]] = {
    (clause["doc_id"], clause["article_no"]): clause for clause in fixtures.POLICY_CLAUSES
}


def clause(doc_id: str, article_no: str) -> dict[str, Any] | None:
    return _BY_KEY.get((doc_id, article_no))


def cite(doc_id: str, article_no: str, score: float | None = None) -> dict[str, Any] | None:
    """取一条可直接返回给前端的引用。取不到就返回 None，调用方要能接受没有依据。"""
    found = clause(doc_id, article_no)
    if found is None:
        return None
    return {
        "doc_id": found["doc_id"],
        "doc_title": found["doc_title"],
        "article_no": found["article_no"],
        "text": found["text"],
        "score": round(float(score if score is not None else found["score"]), 2),
    }


def search(q: str, top_k: int = 3) -> list[dict[str, Any]]:
    """关键词粗筛。D8 换成 混合检索 + 重排，返回结构不变。"""
    keywords = [ch for ch in (q or "") if ch.strip()]
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in fixtures.POLICY_CLAUSES:
        hit = sum(1 for kw in keywords if kw in item["text"])
        scored.append((hit, item))

    matched = [c for hit, c in scored if hit > 0] or [c for _, c in scored]
    matched.sort(key=lambda c: c["score"], reverse=True)
    return matched[:top_k]