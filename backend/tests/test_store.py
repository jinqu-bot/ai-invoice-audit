"""D5 存储与部分成功测试。

这一轮要证明三件事，并且要用"重启"来证明，而不是嘴上说：

1. 批次/发票真的落盘了——关掉连接（等于进程重启）还能读出来
2. 一张失败不再拖垮整批——第 3 张是截图，前两张的成功结果必须还在
3. 台账也是真的——重启之后，同样的票再传一次仍然判"重复报销"

第 3 条是重点：台账在内存里的时候，重启这一下就能把已报过的票洗白。
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import settings
from app.main import app
from app.mock import fixtures
from app.services import db, history, store

client = TestClient(app)


def make_png(seed: int = 0, size: tuple[int, int] = (700, 980)) -> bytes:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i in range(0, size[1], 16):
        d.line([(20, i + seed), (size[0] - 20, i + seed + 2)], fill=(208 - seed, 212, 220))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def restart() -> None:
    """模拟后端重启：断开连接，下次访问重新连到同一个库文件。"""
    db.close()


@pytest.fixture
def mock_model(monkeypatch):
    monkeypatch.setattr(settings, "vlm_api_key", "")
    monkeypatch.setattr(settings, "mock_variant", "")
    return monkeypatch


def upload(*files) -> dict:
    resp = client.post(
        "/api/batches",
        files=[("files", (name, raw, mime)) for name, raw, mime in files],
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------------------------------------------------ 落盘

def test_batch_survives_restart(mock_model):
    body = upload(("a.png", make_png(1), "image/png"))
    batch_id = body["batch_id"]

    before = client.get(f"/api/batches/{batch_id}/results").json()
    assert before["items"], "先确保这一批真的有发票"

    restart()

    after = client.get(f"/api/batches/{batch_id}/results").json()
    assert after["batch"]["batch_id"] == batch_id
    assert after["items"][0]["invoice_id"] == before["items"][0]["invoice_id"]
    assert after["items"][0]["verdict"] == before["items"][0]["verdict"]
    assert after["items"][0]["amount_incl_tax"] == before["items"][0]["amount_incl_tax"]


def test_detail_survives_restart(mock_model):
    body = upload(("a.png", make_png(2), "image/png"))
    invoice_id = client.get(f"/api/batches/{body['batch_id']}/results").json()["items"][0][
        "invoice_id"
    ]
    before = client.get(f"/api/invoices/{invoice_id}").json()

    restart()

    after = client.get(f"/api/invoices/{invoice_id}").json()
    # 轨迹、命中规则、引用、建议都是 JSON 列，重启后必须一字不差地回来
    assert after["trace"] == before["trace"]
    assert after["hit_rules"] == before["hit_rules"]
    assert after["citations"] == before["citations"]
    assert after["suggestions"] == before["suggestions"]
    assert after["fields"] == before["fields"]


def test_uploaded_image_survives_restart(mock_model):
    body = upload(("a.png", make_png(3), "image/png"))
    invoice_id = client.get(f"/api/batches/{body['batch_id']}/results").json()["items"][0][
        "invoice_id"
    ]
    image_url = client.get(f"/api/invoices/{invoice_id}").json()["image_url"]

    restart()

    resp = client.get(image_url)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


# ------------------------------------------------------------------ 台账

def test_duplicate_detected_across_restart(mock_model):
    """重启前后各传一次同一张票，第二次必须还是"重复报销"。

    台账存在内存里时，这一下就洗白了——那 R1 等于没实现。
    """
    first = upload(("same.png", make_png(4), "image/png"))
    first_card = client.get(f"/api/batches/{first['batch_id']}/results").json()["items"][0]
    assert first_card["verdict"] == "pass"
    number = first_card["invoice_number"]
    assert history.find(number) is not None

    restart()

    second = upload(("same.png", make_png(4), "image/png"))
    second_card = client.get(f"/api/batches/{second['batch_id']}/results").json()["items"][0]
    assert second_card["verdict"] == "reject"
    assert "R1" in second_card["hit_rule_codes"]
    assert second_card["invoice_number"] == number


def test_history_seed_restored_after_reset():
    """预置台账就是"重复票怎么造"的答案，重建库之后必须在。"""
    assert history.find("66472890") is not None
    assert history.size() >= 3


# ------------------------------------------------------------------ 部分成功

def test_partial_success_keeps_good_files(mock_model):
    body = upload(
        ("good.png", make_png(5), "image/png"),
        ("note.txt", b"hello", "text/plain"),
    )
    assert body["status"] == "partial"
    assert body["invoice_count"] == 1
    assert [f["filename"] for f in body["failed"]] == ["note.txt"]
    assert body["failed"][0]["code"] == "BAD_IMAGE"

    results = client.get(f"/api/batches/{body['batch_id']}/results").json()
    assert len(results["items"]) == 1
    assert results["items"][0]["filename"] == "good.png"
    assert len(results["failures"]) == 1
    assert results["batch"]["status"] == "partial"
    assert results["batch"]["failed_count"] == 1


def test_all_files_failed_still_opens(mock_model):
    """全失败也要给一个批次号，否则前端只能弹一个 toast，用户看不到"到底哪张错了"。"""
    body = upload(("a.txt", b"x", "text/plain"), ("b.txt", b"y", "text/plain"))
    assert body["status"] == "failed"
    assert body["invoice_count"] == 0
    assert len(body["failed"]) == 2

    results = client.get(f"/api/batches/{body['batch_id']}/results").json()
    assert results["items"] == []
    assert results["batch"]["failed_count"] == 2


def test_failures_survive_restart(mock_model):
    body = upload(("note.txt", b"hello", "text/plain"))
    restart()
    assert store.get_failures(body["batch_id"])[0]["code"] == "BAD_IMAGE"


def test_empty_file_is_reported(mock_model):
    body = upload(("empty.png", b"", "image/png"))
    assert body["status"] == "failed"
    assert body["failed"][0]["code"] == "EMPTY_FILE"


# ------------------------------------------------------------------ 批次号

def test_batch_ids_do_not_repeat_after_restart(mock_model):
    first = store.next_batch_id()
    restart()
    second = store.next_batch_id()
    assert first != second
    assert second.endswith("002") or int(second.split("-")[-1]) > int(first.split("-")[-1])


# ------------------------------------------------------------------ 分页

def test_batch_list_is_paginated(mock_model):
    for index in range(3):
        upload((f"{index}.png", make_png(10 + index), "image/png"))

    page1 = client.get("/api/batches?limit=2&offset=0").json()
    assert page1["limit"] == 2 and page1["offset"] == 0
    assert len(page1["items"]) == 2
    # 演示批次也在里面，所以总数一定含它们
    assert page1["total"] >= 3 + len(fixtures.BATCHES)

    page2 = client.get("/api/batches?limit=2&offset=2").json()
    assert page2["total"] == page1["total"]
    assert {b["batch_id"] for b in page1["items"]}.isdisjoint(
        {b["batch_id"] for b in page2["items"]}
    )


def test_batch_list_rejects_bad_pagination() -> None:
    assert client.get("/api/batches?limit=0").status_code == 422
    assert client.get("/api/batches?offset=-1").status_code == 422


def test_batch_list_still_shows_demo_batches(mock_model) -> None:
    body = client.get("/api/batches?limit=50").json()
    ids = {item["batch_id"] for item in body["items"]}
    assert fixtures.DEMO_BATCH_ID in ids


# ------------------------------------------------------------------ 序号与顺序

def test_results_keep_upload_order(mock_model):
    body = upload(
        ("1.png", make_png(20), "image/png"),
        ("2.png", make_png(21), "image/png"),
        ("3.png", make_png(22), "image/png"),
    )
    results = client.get(f"/api/batches/{body['batch_id']}/results").json()
    assert [item["seq"] for item in results["items"]] == [1, 2, 3]
    assert [item["filename"] for item in results["items"]] == ["1.png", "2.png", "3.png"]