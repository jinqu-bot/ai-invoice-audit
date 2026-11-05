"""抽取链路的单元测试。

重点验三件事：
1. 图片确实被压小了（不然延迟和费用都下不来）
2. 金额勾稽能拦住模型抄错的数字
3. 第一次输出不对时，会把错误回灌给模型重试 —— 这是"输出稳定可控"的证据
"""

from __future__ import annotations

import asyncio
import io
import json

from PIL import Image, ImageDraw

from app.services import llm, validators
from app.services import extract as ex
from app.services.extract import compute_confidence, parse_json
from app.services.image import ImageError, prepare_image


# ------------------------------------------------------------------ 工具

def make_png(size: tuple[int, int] = (1600, 2200)) -> bytes:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i in range(0, size[1], 22):
        d.line([(40, i), (size[0] - 40, i + 4)], fill=(210, 214, 220))
    d.rectangle([60, 60, size[0] - 60, 200], outline=(120, 120, 120))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


VALID = {
    "is_invoice": True,
    "invoice_code": "033002200111",
    "invoice_number": "24815631",
    "invoice_date": "2026-11-01",
    "seller_name": "杭州西溪宾馆有限公司",
    "seller_tax_id": "91330106MA2K7X1A2B",
    "buyer_name": "杭州云帆科技有限公司",
    "buyer_tax_id": "91330100MA2A1B2C3D",
    "amount_excl_tax": 641.51,
    "tax_amount": 38.49,
    "amount_incl_tax": 680.00,
    "tax_rate": 0.06,
    "category": "住宿",
    "items": [{"name": "住宿服务", "amount": 641.51}],
    "confidence": {
        "overall": 0.97,
        "per_field": {
            "invoice_number": 0.99,
            "invoice_date": 0.98,
            "amount_incl_tax": 0.99,
            "seller_name": 0.96,
            "buyer_tax_id": 0.97,
        },
    },
}


# ------------------------------------------------------------------ 图片

def test_prepare_image_downscales():
    raw = make_png((2000, 2600))
    prepared = prepare_image(raw, max_edge=1024)

    assert max(prepared.width, prepared.height) <= 1024
    assert prepared.mime == "image/jpeg"


def test_prepare_image_shrinks_a_photo():
    # 用噪声图模拟手机照片：PNG 压不动，转 JPEG 才有明显收益
    noise = Image.effect_noise((1800, 2400), 64).convert("RGB")
    buf = io.BytesIO()
    noise.save(buf, format="PNG")
    raw = buf.getvalue()

    prepared = prepare_image(raw, max_edge=1024)
    assert prepared.compressed_bytes < len(raw) * 0.5


def test_prepare_image_rejects_garbage():
    try:
        prepare_image(b"not an image at all")
    except ImageError:
        return
    raise AssertionError("非图片应当抛 ImageError")


# ------------------------------------------------------------------ 解析

def test_parse_json_tolerates_code_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_tolerates_chatter():
    assert parse_json('好的，识别结果如下：\n{"a": 1}\n希望有帮助') == {"a": 1}


def test_parse_json_rejects_non_object():
    try:
        parse_json("[1, 2, 3]")
    except ex.ExtractionError:
        return
    raise AssertionError("顶层不是对象时应抛 ExtractionError")


# ------------------------------------------------------------------ 校验

def test_arithmetic_catches_mismatch():
    errors = validators.check_arithmetic(
        {"amount_excl_tax": 100.0, "tax_amount": 6.0, "amount_incl_tax": 200.0}
    )
    assert errors and "勾稽" in errors[0]


def test_arithmetic_allows_one_cent_rounding():
    assert validators.check_arithmetic(
        {"amount_excl_tax": 641.51, "tax_amount": 38.49, "amount_incl_tax": 680.00}
    ) == []


def test_schema_flags_missing_required():
    errors = validators.check_schema({"invoice_number": None})
    assert any("invoice_number" in e for e in errors)


def test_sanity_flags_future_date():
    warnings = validators.check_sanity({"invoice_date": "2099-01-01"})
    assert any("晚于今天" in w for w in warnings)


# ------------------------------------------------------------------ 置信度

def test_confidence_takes_weakest_critical_field():
    data = dict(VALID)
    data["confidence"] = {
        "overall": 0.95,
        "per_field": {
            "invoice_number": 0.99,
            "invoice_date": 0.98,
            "amount_incl_tax": 0.40,
            "seller_name": 0.96,
            "buyer_tax_id": 0.97,
        },
    }
    overall, _ = compute_confidence(data, {"errors": []})
    assert overall == 0.40, "整体把握应取最弱项，而不是平均"


def test_confidence_capped_when_field_missing():
    data = dict(VALID)
    data["invoice_date"] = None
    overall, per = compute_confidence(data, {"errors": []})
    assert per["invoice_date"] <= 0.30
    assert overall <= 0.30


# ------------------------------------------------------------------ 端到端

def test_extract_end_to_end_with_mock_provider(monkeypatch):
    monkeypatch.setattr(ex.settings, "cache_enabled", False)
    result = asyncio.run(ex.extract_one(make_png((900, 1300))))

    assert result.provider == "mock-vlm"
    assert result.is_invoice is True
    assert result.fields.amount_incl_tax in (680.00, 358.00, 78.50)
    assert result.overall_confidence >= 0.8
    assert result.verdict_hint == "pass"
    assert result.validation.errors == []


def test_extract_retries_when_arithmetic_broken(monkeypatch):
    monkeypatch.setattr(ex.settings, "cache_enabled", False)
    calls = {"n": 0}

    broken = dict(VALID)
    broken["amount_incl_tax"] = 999.00  # 和 641.51 + 38.49 对不上

    class FakeProvider(llm.VisionProvider):
        name = "fake"
        model = "fake-1"

        async def chat(self, messages):
            calls["n"] += 1
            payload = broken if calls["n"] == 1 else VALID
            return llm.ChatResult(
                text=json.dumps(payload, ensure_ascii=False),
                provider=self.name,
                model=self.model,
                latency_ms=1,
            )

    monkeypatch.setattr(ex, "get_provider", lambda seed="": FakeProvider())
    result = asyncio.run(ex.extract_one(make_png()))

    assert calls["n"] == 2, "第一次勾稽不过，应当重试一次"
    assert result.retry_count == 1
    assert result.validation.arithmetic_ok
    assert result.verdict_hint == "pass"