"""看板必须读真数据。

D1 起 /api/dashboard 一直返回 fixtures 的 128 张 / 18.6 万，而库里是 0 张——
结果页说 5 张、看板说 128 张，评委点一下就穿。

现在的约束：
1. 库里有票 → 按月份真聚合，source=db；
2. 库里没票 → 退回演示样例，但必须 source=fixture（前端据此标注）；
3. 库里没有部门字段，就返回空数组，不编一个部门分布。
"""

from __future__ import annotations

import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.main import app
from support import upload_and_wait


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_空库退回演示样例但明确标注来源(client):
    body = client.get("/api/dashboard", params={"month": "2020-01"}).json()
    assert body["source"] == "fixture"
    assert body["total_count"] > 0, "空库时给演示样例，不能让页面空着"


def test_有票就按库聚合(client, monkeypatch):
    monkeypatch.setattr(settings, "vlm_api_key", "")
    monkeypatch.setattr(settings, "mock_variant", "0")
    upload_and_wait(client, [
        ("files", ("dash-a.png", _png(), "image/png")),
    ])

    month = date.today().strftime("%Y-%m")
    body = client.get("/api/dashboard", params={"month": month}).json()

    assert body["source"] == "db"
    assert body["total_count"] == 1
    assert body["total_amount"] > 0
    # 库里没有部门字段 —— 不许编
    assert body["by_department"] == []
    # 驳回原因来自命中规则，没命中的票这里可以为空，但字段必须是列表
    assert isinstance(body["reject_reasons"], list)
    assert len(body["daily_trend"]) == 1
