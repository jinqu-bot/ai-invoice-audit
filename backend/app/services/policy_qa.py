"""制度问答（D8）：检索 → 只依据条款回答 → 校验它引用的条号。

这里最容易出的错不是"答不出来"，而是**答得太顺**。
模型很乐意告诉你"住宿费一线城市每晚可报 1200 元"，听起来专业、条理清楚，
但制度里写的是 800——这种错比不回答危险得多，因为用户会照着它去报销。

所以三道闸：
1. 检索不到相关条款，直接说"制度里没有"，不硬答；
2. 只允许用传进去的条款作答，提示词里明确写死；
3. 生成完再回头查它引用的「第 X 条」在不在检索结果里，不在就标记 ungrounded。
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.config import settings
from app.services import policy

_SYSTEM = """你是公司报销制度助手。必须遵守以下规则，违反任何一条都算回答失败：

1. 只能使用【给定的制度条款】回答，不得使用你的常识、经验或任何外部知识；
2. 每个结论后面必须标注依据，格式为「（文件名 第X条）」；
3. 条款里没有写的内容，直接回答「制度未作规定」，并建议咨询财务，禁止推测；
4. 不要编造条款里没有的数字、比例、限额、天数；
5. 回答用中文，简洁，200 字以内。"""

_ARTICLE = re.compile(r"第\s*([0-9一二三四五六七八九十百]+)\s*条")

# 通用词表：这类词出现在任何报销问题里，留着只会把无关问题拽到某条制度上
# （"公司年会抽奖怎么报销"曾经因为命中"公司"被判成与"发票抬头"相关）。
# 6 条制度用一张手写停用词表足够；语料涨到几百条就该换向量检索了。
_STOP = {
    "公司", "报销", "怎么", "么办", "多少", "什么", "可以", "能否", "能不", "不能",
    "能报", "我们", "员工", "是否", "需要", "这个", "那个", "能够", "要求", "如何",
    "哪些", "问题", "情况", "费用", "支出", "标准", "规定", "制度", "吗", "呢",
}


def _tokens(question: str) -> list[str]:
    """中文关键词：连续汉字切成二字组合，够小样本检索用了。"""
    chunks = re.findall(r"[\u4e00-\u9fa5]{2,}", question or "")
    grams: list[str] = []
    for chunk in chunks:
        for i in range(len(chunk) - 1):
            grams.append(chunk[i : i + 2])
    return grams


def retrieve(question: str, top_k: int = 3) -> list[dict[str, Any]]:
    """检索相关条款。返回空列表表示「制度里没有相关内容」——调用方必须能接受。

    **难点不是找到相关条款，而是敢于说「没有」。**
    第一版按"任意二字组合命中"检索，结果"公司年会抽奖怎么报销"也能匹配上——
    因为"公司""报销"这两个词每条制度里都有，等于没有区分度。
    现在按文档频率自动剔除这种高频词，再要求至少命中两个有效词。
    """
    grams = _tokens(question)
    if not grams:
        return []

    clauses = policy.search(question, top_k=99)
    total = len(clauses) or 1
    df = {
        gram: sum(1 for clause in clauses if gram in clause["text"])
        for gram in set(grams)
    }
    # 出现在过半条款里的二字组合没有区分度，直接当停用词丢掉
    informative = [
        gram for gram, count in df.items()
        if 0 < count * 2 <= total and gram not in _STOP
    ]
    if not informative:
        return []
    # 至少命中一个"只属于某一条"的词才算真相关。
    # 否则"公司 + 报销"这种到处都有的词能把任何问题拽到某条制度上。
    specific = {gram for gram in informative if df[gram] == 1}

    need = 2 if len(informative) >= 2 else 1
    scored: list[tuple[int, dict[str, Any]]] = []
    for clause in clauses:
        matched = [gram for gram in informative if gram in clause["text"]]
        if len(matched) < need:
            continue
        if not any(gram in specific for gram in matched):
            continue
        scored.append((len(matched), clause))

    scored.sort(key=lambda pair: (pair[0], pair[1].get("score", 0)), reverse=True)
    return [clause for _, clause in scored[:top_k]]


def _grounded_articles(answer: str, clauses: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """模型引用的条号必须出现在检索结果里，否则说明它在编。"""
    def normalize(text: str) -> str:
        return re.sub(r"\s+", "", text)

    allowed = {normalize(clause["article_no"]) for clause in clauses}
    cited = {f"第{num}条" for num in _ARTICLE.findall(normalize(answer))}
    invented = sorted(cited - allowed)
    return (not invented), invented


def _call_model(question: str, clauses: list[dict[str, Any]]) -> tuple[str, str, int]:
    """返回 (答案, 模型名, 耗时 ms)。没配 key 时抛 LookupError，由调用方降级。"""
    if not (settings.llm_api_key and settings.llm_base_url):
        raise LookupError("text model not configured")

    context = "\n\n".join(
        f"【{clause['doc_title']} {clause['article_no']}】{clause['text']}" for clause in clauses
    )
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"制度条款：\n{context}\n\n问题：{question}"},
        ],
        "temperature": 0,
        # 推理型模型会把 token 先花在思考上，给小了正文会是空的（在识别那边踩过）
        "max_tokens": max(2000, settings.llm_max_tokens),
    }
    started = time.perf_counter()
    with httpx.Client(timeout=settings.llm_timeout_s) as client:
        response = client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=payload,
        )
    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        raise RuntimeError(f"模型返回 HTTP {response.status_code}：{response.text[:200]}")
    data = response.json()
    answer = (data["choices"][0]["message"]["content"] or "").strip()
    if not answer:
        raise RuntimeError("模型返回了空内容")
    return answer, settings.llm_model, latency


def answer(question: str, top_k: int = 3) -> dict[str, Any]:
    """问答主流程。任何一步出问题都要退回到「只给条款原文」，绝不编。"""
    clauses = retrieve(question, top_k=top_k)

    if not clauses:
        return {
            "question": question,
            "answer": "现行制度里没有找到与这个问题相关的条款。建议直接咨询财务确认，"
            "不要按经验判断——制度没有规定的，就是需要人来决定的事。",
            "citations": [],
            "grounded": True,
            "refused": True,
            "provider": "rules-only",
            "model": "",
            "latency_ms": 0,
            "warning": "",
        }

    try:
        text, model, latency = _call_model(question, clauses)
        grounded, invented = _grounded_articles(text, clauses)
        warning = ""
        if not grounded:
            warning = (
                f"模型的回答引用了检索结果里不存在的条款（{'、'.join(invented)}），"
                "这条回答不可信，请以左侧条款原文为准。"
            )
        return {
            "question": question,
            "answer": text,
            "citations": clauses,
            "grounded": grounded,
            "refused": False,
            "provider": "openai-compat",
            "model": model,
            "latency_ms": latency,
            "warning": warning,
        }
    except (LookupError, RuntimeError, KeyError, httpx.HTTPError) as exc:
        # 降级：不生成结论，只把条款原文摆出来让用户自己看。
        # 这比"编一个看着像答案的答案"诚实得多。
        return {
            "question": question,
            "answer": "当前没有接入文本模型，下面是检索到的条款原文，请以原文为准。",
            "citations": clauses,
            "grounded": True,
            "refused": False,
            "provider": "retrieval-only",
            "model": "",
            "latency_ms": 0,
            "warning": f"模型不可用（{exc}），已降级为只返回原文。",
        }
