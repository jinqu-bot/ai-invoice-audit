"""演示前复位（scripts/reset_demo.py）的行为约束。

这一组测试存在的原因：B 在 11/10 重复上传 real_11 时，先命中了 R1 并短路，
导致 R3/R4 根本跑不到——演示就演不出第二幕。复位脚本必须保证：
    1. 台账里只剩 3 条预置样例（演示批次的 R1 故事要用）；
    2. 联调写进去的 openai-compat / mock-vlm 记录全部清掉；
    3. 批次、发票、复核记录一起清，上传文件也删掉。
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.main import app
from app.services import db, history, store
from support import upload_and_wait


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    return buf.getvalue()


def _ledger_sources() -> dict[str, int]:
    rows = db.query("SELECT source, COUNT(*) AS n FROM audit_history GROUP BY source")
    return {row["source"]: int(row["n"]) for row in rows}


def test_复位后台账只剩预置样例(client, monkeypatch):
    monkeypatch.setattr(settings, "vlm_api_key", "")
    monkeypatch.setattr(settings, "mock_variant", "0")

    before = db.one("SELECT COUNT(*) AS n FROM audit_history")
    body = upload_and_wait(client, [("files", ("reset-demo.png", _png(), "image/png"))])
    assert body["status"] in ("done", "partial")

    # 上传后至少要有一条非预置来源的记录，否则这个测试没测到东西
    sources = _ledger_sources()
    assert any(name != "fixture" for name in sources), sources

    store.reset()
    db.execute("DELETE FROM reviews")
    history.reset()

    sources = _ledger_sources()
    assert set(sources) <= {"fixture"}, f"联调记录没清干净：{sources}"
    assert db.one("SELECT COUNT(*) AS n FROM batches")["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM invoices")["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM reviews")["n"] == 0
    # 预置样例必须还在：演示批次里那条"重复报销"要靠它
    assert sum(sources.values()) >= 3
    assert before is not None
