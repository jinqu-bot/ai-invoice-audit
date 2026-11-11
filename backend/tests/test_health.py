"""健康检查必须能看出"模型是不是真的能用"。

11/11 踩过一次：DeepSeek 账户余额 -0.01，`recognition_provider` 照样报 `openai-compat`，
`/api/health` 全绿，直到用户上传才炸。配着 key 不等于模型能用。

这里不探活（每次探活都要花钱），只在真实调用时记一笔：
- 失败（402 欠费 / 401 鉴权 / 超时 / 网络）→ `last_error` 有值、`consecutive_failures` +1
- 成功一次 → 清空，`model_ok=true`
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import model_health


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_初始状态不给绿灯(client):
    """还没调用过就说"模型好着"，等于没检查。"""
    body = client.get("/api/health").json()
    assert body["model_ok"] is False
    assert body["last_error"] is None


def test_失败之后健康检查要说出原因(client):
    model_health.record_failure(
        '模型返回 HTTP 402：{"error":{"message":"Insufficient Balance"}}'
    )
    body = client.get("/api/health").json()
    assert body["model_ok"] is False
    assert body["consecutive_failures"] == 1
    assert "402" in body["last_error"]
    assert "Insufficient Balance" in body["last_error"]


def test_连续失败会累加(client):
    for _ in range(3):
        model_health.record_failure("模型调用超时（90s）")
    assert client.get("/api/health").json()["consecutive_failures"] == 3


def test_成功一次就清掉错误(client):
    model_health.record_failure("模型返回 HTTP 401：invalid api key")
    model_health.record_ok()
    body = client.get("/api/health").json()
    assert body["model_ok"] is True
    assert body["last_error"] is None
    assert body["consecutive_failures"] == 0
    assert body["last_ok_at"]


def test_网络错误也会被记下来(client, monkeypatch):
    """不只是 HTTP 4xx/5xx：超时和网络异常同样要进健康检查。"""
    import asyncio

    import httpx

    from app.services.llm import OpenAICompatVision, ProviderError

    monkeypatch.setattr(settings, "vlm_api_key", "sk-test")
    provider = OpenAICompatVision()

    class Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: Boom())
    with pytest.raises(ProviderError):
        asyncio.run(provider._post({}))
    body = client.get("/api/health").json()
    assert "网络错误" in body["last_error"]