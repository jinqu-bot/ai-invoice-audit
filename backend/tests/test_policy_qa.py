"""制度问答（D8）的契约测试。

重点不是"能回答"，而是**它在不知道的时候会不会胡说**。
一个会编限额的制度助手，比没有助手危险得多——用户会照着它去报销。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import policy_qa

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    """默认把模型关掉：测试不能依赖网络，也不该花钱。"""
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", "")
    yield


def test_retrieval_finds_the_hotel_clause():
    clauses = policy_qa.retrieve("住宿费超标了还能报吗")
    assert clauses, "住宿问题必须能检索到条款"
    assert any("住宿" in clause["text"] for clause in clauses)


def test_without_model_it_returns_raw_clauses_not_a_guess():
    """没接模型时必须明说“只给原文”，不能假装回答了。"""
    response = client.get("/api/policies/ask", params={"q": "住宿费超标怎么办"})
    assert response.status_code == 200
    body = response.json()

    assert body["provider"] == "retrieval-only"
    assert body["citations"], "降级也要把条款摆出来"
    assert "条款原文" in body["answer"]
    assert body["model"] == ""


def test_question_outside_the_policy_is_refused():
    """制度里没有的事（加班费），必须明确说没有——这是最容易翻车的地方。"""
    body = client.get("/api/policies/ask", params={"q": "加班费怎么算"}).json()
    assert body["refused"] is True
    assert body["citations"] == []
    assert body["grounded"] is True, "拒绝回答本身是诚实的，不算编造"


def test_empty_question_is_rejected():
    assert client.get("/api/policies/ask", params={"q": " "}).status_code == 422


def test_model_answer_is_checked_against_retrieved_clauses(monkeypatch):
    """模型编了一个不存在的条号，必须被抓住并标记 ungrounded。"""

    def fake_model(question, clauses):
        # 故意引用 第99条 —— 检索结果里没有这条
        return "一线城市住宿每晚可报 1200 元（差旅费管理办法 第99条）", "fake-model", 12

    monkeypatch.setattr(policy_qa, "_call_model", fake_model)
    body = client.get("/api/policies/ask", params={"q": "住宿费超标怎么办"}).json()

    assert body["grounded"] is False
    assert "第99条" in body["warning"]
    assert body["provider"] == "openai-compat"


def test_grounded_answer_passes_the_check(monkeypatch):
    """如实引用检索到的条号，应当通过校验。"""
    clauses = policy_qa.retrieve("住宿费超标怎么办")
    real = clauses[0]

    def fake_model(question, clauses):
        return f"按制度，一线城市住宿标准为每晚 800 元（{real['doc_title']} {real['article_no']}）。", "fake-model", 9

    monkeypatch.setattr(policy_qa, "_call_model", fake_model)
    body = client.get("/api/policies/ask", params={"q": "住宿费超标怎么办"}).json()

    assert body["grounded"] is True
    assert body["warning"] == ""
    assert body["provider"] == "openai-compat"
    assert body["latency_ms"] == 9


def test_model_failure_falls_back_to_clauses(monkeypatch):
    """模型超时/报错时，不能抛 500，也不能编——退回只给原文。"""

    def boom(question, clauses):
        raise RuntimeError("模型返回 HTTP 500：upstream error")

    monkeypatch.setattr(policy_qa, "_call_model", boom)
    body = client.get("/api/policies/ask", params={"q": "住宿费超标怎么办"}).json()

    assert body["provider"] == "retrieval-only"
    assert "降级" in body["warning"]
    assert body["citations"]
