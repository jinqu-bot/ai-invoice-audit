"""补测：缓存命中标记必须一路透到结果卡片上（不只是详情）

D7 复验时发现：详情 payload 里 cached=True，但卡片走的是 _CARD_KEYS 白名单，
cached 不在里面，于是结果页拿到的是默认 False——同一件事两个接口两种说法。
"""

from __future__ import annotations

import io

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


def test_卡片与详情对缓存标记说法一致(client, monkeypatch):
    monkeypatch.setattr(settings, "vlm_api_key", "")
    monkeypatch.setattr(settings, "mock_variant", "0")
    monkeypatch.setattr(settings, "cache_enabled", True)

    image = _png()
    first = upload_and_wait(client, [("files", ("cache-a.png", image, "image/png"))])
    second = upload_and_wait(client, [("files", ("cache-b.png", image, "image/png"))])

    first_card = client.get(f"/api/batches/{first['batch_id']}/results").json()["items"][0]
    second_card = client.get(f"/api/batches/{second['batch_id']}/results").json()["items"][0]
    second_detail = client.get(f"/api/invoices/{second_card['invoice_id']}").json()

    assert first_card["cached"] is False
    assert second_card["cached"] is True, "第二次同图必须标成缓存命中"
    assert second_detail["cached"] is True, "卡片说缓存、详情说真调用，等于骗人"
    # 缓存命中的那张，延迟应该明显更小；这条是给"几毫秒出结果"的解释兜底
    assert second_card["latency_ms"] <= first_card["latency_ms"]
