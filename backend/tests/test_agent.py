"""函数调用（让模型自己决定查什么）的测试。

这一层最容易变成"演 Agent"：模型其实什么都没决定，代码写死顺序却画成"AI 在规划"。
所以测试盯三件事：
1. 模型选了什么，就执行什么（顺序、参数都照它的来）；
2. 模型不调工具 → 退回固定顺序，且 `by=fallback` 必须标出来；
3. 叫不出名字的工具要如实报错，不能假装调用过。

另外四条边界：没有真模型时 503；工具内部异常不能带崩整轮；
`search_policy` 查不到必须说"没有"；`check_duplicate` 必须查真台账。
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.main import app
from app.services import agent, history
from app.services.llm import ProviderError
from support import upload_and_wait


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _detail(**overrides):
    detail = {
        "invoice_id": "INV-X",
        "provider": "openai-compat",
        "fields": {
            "invoice_number": "24815631",
            "invoice_code": "033002200111",
            "invoice_date": "2026-11-01",
            "seller_name": "杭州西溪宾馆有限公司",
            "buyer_name": "杭州云帆科技有限公司",
            "amount_incl_tax": 680.0,
            "amount_excl_tax": 641.51,
            "tax_amount": 38.49,
            "tax_rate": 0.06,
            "category": "住宿",
        },
    }
    detail.update(overrides)
    return detail


class FakeProvider:
    """按剧本返回 tool_calls 的假模型。剧本里每个元素是"这一轮要调哪些工具"。"""

    name = "openai-compat"
    model = "fake-tool-model"

    def __init__(self, script: list[list[tuple[str, dict]]], final: str = ""):
        self.script = script
        self.final = final
        self.calls: list[list[dict]] = []

    async def chat_tools(self, messages, tools):
        self.calls.append(messages)
        index = len(self.calls) - 1
        if index >= len(self.script):
            return {"role": "assistant", "content": self.final or "查完了，建议转人工。"}, 7
        calls = [
            {
                "id": f"call_{index}_{i}",
                "type": "function",
                "function": {"name": name, "arguments": __import__("json").dumps(args)},
            }
            for i, (name, args) in enumerate(self.script[index])
        ]
        return {"role": "assistant", "content": "", "tool_calls": calls}, 9


def test_模型选什么就执行什么(monkeypatch):
    provider = FakeProvider(
        script=[[("get_threshold", {"category": "住宿"})]],
        final="住宿上限 800，这张 680 没超。",
    )
    result = __import__("asyncio").run(agent.plan(_detail(), provider))
    assert result["fallback"] is False
    assert [s["tool"] for s in result["steps"]] == ["get_threshold"]
    assert result["steps"][0]["by"] == "model"
    assert result["steps"][0]["result"]["limit"] == 800.0
    assert "800" in result["summary"]
    assert result["rounds"] == 2


def test_模型不调工具就退回固定顺序并标出来():
    provider = FakeProvider(script=[[],], final="看起来没问题。")
    result = __import__("asyncio").run(agent.plan(_detail(), provider))
    assert result["fallback"] is True
    assert [s["tool"] for s in result["steps"]] == list(agent.DEFAULT_ORDER)
    assert all(s["by"] == "fallback" for s in result["steps"])
    # 兜底时不能把模型的空判断当成审核结论
    assert "主链路" in result["summary"]


def test_未知工具如实报错不假装调用():
    provider = FakeProvider(script=[[("delete_everything", {})],])
    result = __import__("asyncio").run(agent.plan(_detail(), provider))
    step = result["steps"][0]
    assert step["tool"] == "delete_everything"
    assert step["result"]["ok"] is False
    assert "没有这个工具" in step["result"]["reason"]
    assert result["fallback"] is False  # 它确实调了，只是调错名字


def test_查重查的是真台账(monkeypatch):
    # 往台账里塞一条，工具必须能查出来（不是返回假数据）
    history.remember(
        {"invoice_number": "24815631", "seller_name": "杭州西溪宾馆有限公司",
         "amount_incl_tax": 680.0, "invoice_date": "2026-11-01"},
        verdict="pass", batch_id="B-TEST", invoice_id="INV-Y", source="openai-compat",
    )
    provider = FakeProvider(script=[[("check_duplicate", {"invoice_number": "24815631"})],])
    result = __import__("asyncio").run(agent.plan(_detail(), provider))
    assert result["steps"][0]["result"]["hit"] is True
    assert result["steps"][0]["result"]["reimbursement_no"]


def test_制度查不到就说没有():
    provider = FakeProvider(script=[[("search_policy", {"query": "年会抽奖怎么报销"})],])
    result = __import__("asyncio").run(agent.plan(_detail(), provider))
    step = result["steps"][0]
    assert step["result"]["ok"] is True
    if step["result"]["found"] == 0:
        assert "没有找到" in step["result"]["note"]


def test_没有真模型时接口直接503(client, monkeypatch):
    monkeypatch.setattr(settings, "vlm_api_key", "")
    response = client.post("/api/invoices/INV-0001/agent-plan")
    assert response.status_code == 503
    assert "函数调用需要真实模型" in response.json()["message"]


def test_发票不存在时404(client):
    assert client.post("/api/invoices/NOT-EXIST/agent-plan").status_code == 404


def test_工具抛异常不带崩整轮(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("台账挂了")

    monkeypatch.setattr(agent.history, "find", boom)
    provider = FakeProvider(script=[[("check_duplicate", {"invoice_number": "24815631"})],])
    result = __import__("asyncio").run(agent.plan(_detail(), provider))
    step = result["steps"][0]
    assert step["result"]["ok"] is False
    assert "台账挂了" in step["result"]["reason"]
