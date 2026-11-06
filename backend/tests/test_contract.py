"""前后端契约测试。

跑的是真实路由 + FastAPI 的 response_model 校验，所以能拦住一类很阴的 bug：
数据在生产路径里长得对，但不符合 schemas.py，线上直接 500。

这正是 B 联调时提的第 2 条（store 产出 warn、契约里没有 warn）——
单元测试全绿，页面一打开就崩。
"""

from __future__ import annotations

import io
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import _load_dotenv, settings
from app.main import app
from app.mock import fixtures
from app.schemas import TraceStatus
from app.services import store

client = TestClient(app)

VALID_STATUSES = set(get_args(TraceStatus))
DEMO_BATCH = "B20261104-001"


# ------------------------------------------------------------------ 工具

def make_png(size: tuple[int, int] = (800, 1100)) -> bytes:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i in range(0, size[1], 18):
        d.line([(30, i), (size[0] - 30, i + 3)], fill=(215, 219, 225))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def use_mock_provider(monkeypatch) -> None:
    """把 provider 钉死在 mock，避免本机 .env 里有真 key 时测试去打网络。"""
    monkeypatch.setattr(settings, "vlm_api_key", "")


def find_fixture_invoice(verdict: str) -> str:
    for batch_id in fixtures.BATCHES:
        for card in fixtures.items_of(batch_id):
            if card["verdict"] == verdict:
                return card["invoice_id"]
    raise AssertionError(f"演示数据里没有 {verdict} 的发票")


# ------------------------------------------------------------------ 基础

def test_health_ok() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["stage"]


def test_demo_batch_results_valid() -> None:
    resp = client.get(f"/api/batches/{DEMO_BATCH}/results")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["batch"]["invoice_count"] == 5
    assert body["batch"]["pass_count"] == 3
    assert body["batch"]["suspect_count"] == 1
    assert body["batch"]["reject_count"] == 1
    # 演示数据不是模型跑出来的，来源必须如实标成 fixture，不能冒充真模型
    assert body["batch"]["provider"] == "fixture"


@pytest.mark.parametrize("verdict", ["pass", "suspect", "reject", "manual"])
def test_fixture_detail_valid_for_every_verdict(verdict: str) -> None:
    invoice_id = find_fixture_invoice(verdict)
    resp = client.get(f"/api/invoices/{invoice_id}")
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["verdict"] == verdict
    assert all(step["status"] in VALID_STATUSES for step in detail["trace"])


# ------------------------------------------------------------------ 真实上传

def test_real_upload_then_detail_valid(monkeypatch) -> None:
    use_mock_provider(monkeypatch)
    resp = client.post(
        "/api/batches",
        files={"files": ("inv.png", make_png(), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["batch_id"]

    summary = client.get(f"/api/batches/{batch_id}").json()
    assert summary["provider"] == "mock-vlm"

    results = client.get(f"/api/batches/{batch_id}/results").json()
    invoice_id = results["items"][0]["invoice_id"]

    detail = client.get(f"/api/invoices/{invoice_id}").json()
    assert all(step["status"] in VALID_STATUSES for step in detail["trace"])


def test_low_confidence_goes_manual_and_detail_survives(monkeypatch) -> None:
    """置信度阈值拉到 1.0，强制走转人工分支。

    这条是 B 提的 warn 问题的回归测试：以前这里详情接口会 500。
    """
    use_mock_provider(monkeypatch)
    monkeypatch.setattr(settings, "confidence_threshold", 1.0)

    resp = client.post(
        "/api/batches",
        files={"files": ("blur.png", make_png((600, 800)), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["batch_id"]
    invoice_id = client.get(f"/api/batches/{batch_id}/results").json()["items"][0]["invoice_id"]

    detail_resp = client.get(f"/api/invoices/{invoice_id}")
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()

    assert detail["verdict"] == "manual"
    assert detail["manual_review"] is True
    assert detail["hit_rule_codes"] == ["R0"]
    assert any(step["status"] == "warn" for step in detail["trace"])
    assert detail["missing_fields"] == [] or isinstance(detail["missing_fields"], list)


def test_batch_provider_is_not_fixture_for_real_upload(monkeypatch) -> None:
    use_mock_provider(monkeypatch)
    batch = store.build_batch(
        "B-TEST-PROVIDER",
        [("a.png", "img", _fake_extraction(provider="openai-compat"))],
    )
    assert batch.summary["provider"] == "openai-compat"

    mixed = store.build_batch(
        "B-TEST-MIXED",
        [
            ("a.png", "img", _fake_extraction(provider="openai-compat")),
            ("b.png", "img", _fake_extraction(provider="mock-vlm")),
        ],
    )
    assert mixed.summary["provider"] == "mixed"


def _fake_extraction(provider: str):
    from app.services.extract import ExtractionResult  # 局部导入，避免顶层循环依赖
    from app.schemas import ExtractedFields, FieldConfidence, ImageMeta, ValidationReport

    return ExtractionResult(
        extraction_id="x",
        is_invoice=True,
        fields=ExtractedFields(invoice_number="24815631", amount_incl_tax=680.0),
        field_confidence=FieldConfidence(overall=0.9, per_field={}),
        overall_confidence=0.9,
        verdict_hint="pass",
        validation=ValidationReport(),
        provider=provider,
        model="test",
        cached=False,
        retry_count=0,
        latency_ms=10,
        image=ImageMeta(
            sha256="0" * 64,
            original_bytes=1,
            compressed_bytes=1,
            width=10,
            height=10,
            mime="image/png",
        ),
    )


def test_missing_fields_reported(monkeypatch) -> None:
    """没识别出来的字段要单独报出来，否则 0.00 会被当成真实金额。"""
    from app.schemas import ExtractedFields

    ext = _fake_extraction(provider="mock-vlm")
    ext.fields = ExtractedFields(invoice_number="24815631")  # 其余全空

    batch = store.build_batch("B-TEST-MISSING", [("a.png", "img", ext)])
    detail = batch.details["INV-B-TEST-MISSING-01"]
    assert "amount_incl_tax" in detail["missing_fields"]
    assert "seller_name" in detail["missing_fields"]


# ------------------------------------------------------------------ 错误形状

def test_mock_can_simulate_non_invoice(monkeypatch) -> None:
    """把 mock 钉在"不是发票"上，验证这条分支走得通。

    C 交了两张非发票图片，但 mock 根本不看图片内容——它的输出只跟指纹有关。
    所以"拿非发票图跑 mock，看它能不能认出来"这件事是假的。要验的是分支：
    is_invoice=False 时结论必须是 manual，而且理由要说人话。
    """
    use_mock_provider(monkeypatch)
    monkeypatch.setattr(settings, "mock_variant", "non_invoice")
    monkeypatch.setattr(settings, "cache_enabled", False)

    resp = client.post(
        "/api/batches",
        files={"files": ("chat.png", make_png((500, 700)), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["batch_id"]
    card = client.get(f"/api/batches/{batch_id}/results").json()["items"][0]

    assert card["verdict"] == "manual"
    assert card["manual_review"] is True
    assert "没有可识别的发票" in card["headline"]

    detail = client.get(f"/api/invoices/{card['invoice_id']}").json()
    assert "amount_incl_tax" in detail["missing_fields"]
    assert detail["trace"][0]["status"] == "error", "第一关就该标出这不是发票"


def test_422_has_unified_shape() -> None:
    """缺必填查询参数时，前端也要能按 code/message 解析。"""
    resp = client.get("/api/policies/search")  # 故意不带 q
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "q" in body["message"]
    assert isinstance(body["details"], list) and body["details"]


def test_non_image_upload_is_reported_not_fatal() -> None:
    """D5 改了契约：非图片不再整批 400，而是"这批失败，原因写在 failed 里"。

    理由：一次传 5 张、第 3 张是微信截图时，把前两张的成功结果一起丢掉是很糟的体验。
    """
    resp = client.post(
        "/api/batches",
        files={"files": ("note.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["invoice_count"] == 0
    assert body["failed"][0]["filename"] == "note.txt"
    assert body["failed"][0]["code"] == "BAD_IMAGE"
    assert "不是图片" in body["failed"][0]["message"]


def test_extract_rejects_non_image() -> None:
    resp = client.post("/api/extract", files={"file": ("note.txt", b"hello", "text/plain")})
    assert resp.status_code == 400


# ------------------------------------------------------------------ 配置加载

def test_dotenv_loader(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("D2_TEST_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# 注释行应被忽略\n"
        "D2_TEST_KEY=abc123\n"
        "D2_QUOTED='带引号'\n"
        # 行尾注释必须切掉：.env.example 里就是这种写法，切不干净会让 int() 直接崩
        "D2_TRAILING=1024        # 长边压到这个尺寸\n"
        "坏行没有等号\n",
        encoding="utf-8",
    )
    _load_dotenv(env)

    import os

    assert os.environ["D2_TEST_KEY"] == "abc123"
    assert os.environ["D2_QUOTED"] == "带引号"
    assert os.environ["D2_TRAILING"] == "1024"
    assert int(os.environ["D2_TRAILING"]) == 1024, "行尾注释不能混进数值"
    for key in ("D2_TEST_KEY", "D2_QUOTED", "D2_TRAILING"):
        monkeypatch.delenv(key, raising=False)