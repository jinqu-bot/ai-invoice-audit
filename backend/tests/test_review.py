"""人工复核（D8）的契约测试。

这一层的要害不是"能改判"，而是**改判必须留痕、并且不许悄悄覆盖**：
机器说驳回，人改成通过，系统里必须两句话都留着。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import db, jobs

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean() -> None:
    jobs.reset()
    db.execute("DELETE FROM reviews")
    yield
    db.execute("DELETE FROM reviews")


def _first_invoice(batch_id: str = "B20261104-001") -> dict:
    body = client.get(f"/api/batches/{batch_id}/results").json()
    return body["items"][0]


def test_review_flips_the_verdict_and_keeps_both_sides() -> None:
    card = _first_invoice()
    invoice_id = card["invoice_id"]
    before = card["verdict"]

    response = client.post(
        f"/api/invoices/{invoice_id}/review",
        json={"action": "pass", "reason": "抬头已补开发票，财务确认", "reviewer": "张会计"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["verdict"] == "pass"
    assert body["reviewed"] is True
    assert "人工复核通过" in body["headline"]
    assert body["reviews"][-1]["verdict_before"] == before
    assert body["reviews"][-1]["verdict_after"] == "pass"
    assert body["reviews"][-1]["reviewer"] == "张会计"


def test_reviewed_verdict_shows_up_in_the_batch_list() -> None:
    """列表和详情不能互相打脸：详情改成 pass，列表还显示 reject 就穿帮了。"""
    card = _first_invoice()
    invoice_id = card["invoice_id"]

    client.post(
        f"/api/invoices/{invoice_id}/review",
        json={"action": "pass", "reason": "财务已核对原件", "reviewer": ""},
    )

    items = client.get("/api/batches/B20261104-001/results").json()["items"]
    updated = next(item for item in items if item["invoice_id"] == invoice_id)
    assert updated["verdict"] == "pass"
    assert updated["reviewed"] is True


def test_reason_is_mandatory() -> None:
    """没有理由的改判等于没留痕——直接在参数校验这一层拦掉。"""
    card = _first_invoice()
    response = client.post(
        f"/api/invoices/{card['invoice_id']}/review",
        json={"action": "pass", "reason": ""},
    )
    assert response.status_code == 422


def test_unknown_invoice_cannot_be_reviewed() -> None:
    response = client.post(
        "/api/invoices/INV-NOT-EXIST/review",
        json={"action": "pass", "reason": "测试"},
    )
    assert response.status_code == 404


def test_second_review_keeps_the_first_one() -> None:
    """改判两次要能看到两条轨迹：谁先改的、谁又改回去的。"""
    card = _first_invoice()
    invoice_id = card["invoice_id"]

    client.post(f"/api/invoices/{invoice_id}/review",
                json={"action": "pass", "reason": "第一次改判", "reviewer": "张会计"})
    body = client.post(f"/api/invoices/{invoice_id}/review",
                       json={"action": "reject", "reason": "复核后发现是同一张票", "reviewer": "李主管"}).json()

    assert body["verdict"] == "reject"
    assert len(body["reviews"]) == 2
    assert [r["verdict_after"] for r in body["reviews"]] == ["pass", "reject"]
    assert body["reviews"][1]["verdict_before"] == "pass"


def test_reviewer_defaults_to_placeholder_not_a_real_name() -> None:
    """没填名字就写“未登记”，不要编一个“报销人”出来——上次就是这么翻车的。"""
    card = _first_invoice()
    body = client.post(
        f"/api/invoices/{card['invoice_id']}/review",
        json={"action": "manual", "reason": "要素看不清，转人工"},
    ).json()
    assert body["reviews"][-1]["reviewer"] == "未登记"
    assert "报销人" not in body["headline"]
