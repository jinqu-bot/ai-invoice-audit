"""规则引擎测试（D4）。

每条规则都要验两件事：**该命中时命中，不该命中时别乱叫**。
只测前者的话，最后会得到一个"什么票都驳回"的系统，看着很严格，实际不能用。
"""

from __future__ import annotations

from datetime import date, timedelta

from app.company import COMPANY_NAME, COMPANY_TAX_ID
from app.schemas import ExtractedFields, FieldConfidence, ImageMeta, InvoiceItem, ValidationReport
from app.services import history, rules, store
from app.services.rules import run_audit
from app.schemas import ExtractionResult


# ------------------------------------------------------------------ 工具

def make_fields(**overrides) -> ExtractedFields:
    base = {
        "invoice_code": "033002200198",
        "invoice_number": "88880001",
        "invoice_date": date.today().isoformat(),
        "seller_name": "杭州西溪宾馆有限公司",
        "seller_tax_id": "91330106MA2K7X1A2B",
        "buyer_name": COMPANY_NAME,
        "buyer_tax_id": COMPANY_TAX_ID,
        "amount_excl_tax": 641.51,
        "tax_amount": 38.49,
        "amount_incl_tax": 680.00,
        "tax_rate": 0.06,
        "category": "住宿",
        "items": [InvoiceItem(name="住宿费", amount=641.51)],
    }
    base.update(overrides)
    return ExtractedFields(**base)


def make_extraction(fields: ExtractedFields | None = None, confidence: float = 0.95,
                    is_invoice: bool = True, errors: list[str] | None = None) -> ExtractionResult:
    fields = fields or make_fields()
    return ExtractionResult(
        extraction_id="test",
        is_invoice=is_invoice,
        fields=fields,
        field_confidence=FieldConfidence(overall=confidence, per_field={}),
        overall_confidence=confidence,
        verdict_hint="pass" if confidence >= 0.8 and is_invoice else "manual",
        validation=ValidationReport(errors=errors or []),
        provider="mock-vlm",
        model="mock-vlm-1",
        cached=False,
        retry_count=0,
        latency_ms=120,
        image=ImageMeta(
            sha256="0" * 64, original_bytes=1, compressed_bytes=1,
            width=10, height=10, mime="image/png",
        ),
    )


def audit(fields: ExtractedFields | None = None, *, confidence: float = 0.95,
          is_invoice: bool = True, errors: list[str] | None = None):
    return run_audit(
        fields or make_fields(),
        confidence=confidence,
        is_invoice=is_invoice,
        history=history,
        validation_errors=errors,
    )


def codes(result) -> list[str]:
    return [hit["code"] for hit in result.hits]


# ------------------------------------------------------------------ 正常票

def test_clean_invoice_passes():
    result = audit()
    assert result.verdict == "pass"
    assert result.hits == []
    assert result.citations == []
    assert "通过" in result.headline


def test_pass_does_not_emit_noise():
    """干净票不该有任何命中，否则审核员会开始无视红灯。"""
    result = audit(make_fields(amount_incl_tax=680.0, amount_excl_tax=641.51))
    assert result.verdict == "pass", codes(result)


# ------------------------------------------------------------------ R1 查重

def test_duplicate_invoice_is_rejected():
    seeded = history.find("66472890")
    assert seeded is not None, "台账应当预置演示用的历史单据"
    result = audit(make_fields(invoice_number="66472890", invoice_code="033002200115"))

    assert result.verdict == "reject"
    assert "R1" in codes(result)
    hit = next(h for h in result.hits if h["code"] == "R1")
    assert "BX-1102-007" in hit["detail"]
    assert "张伟" in hit["detail"]


def test_duplicate_short_circuits_other_checks():
    """命中重复后不应该继续核标准——"会停"本身就是能力。"""
    result = audit(make_fields(
        invoice_number="66472890",
        amount_incl_tax=9999.0,  # 同时超标，但查重已命中
    ))
    tools = [step["tool"] for step in result.trace]
    assert "short_circuit" in tools
    assert "check_standard" not in tools
    assert "R5" not in codes(result)


def test_same_invoice_twice_in_one_batch():
    """同一批里重复上传两张，第二张必须被查出来。"""
    ext = make_extraction(make_fields(invoice_number="77776666"))
    batch = store.build_batch("B-DUP-TEST", [("a.png", "img1", ext), ("b.png", "img2", ext)])

    verdicts = [card["verdict"] for card in batch.cards]
    assert verdicts == ["pass", "reject"]
    assert batch.summary["reject_count"] == 1


def test_rejected_invoice_is_not_written_to_ledger():
    """被驳回的票不入账，否则重开后再报会被误判成重复。"""
    bad = make_fields(invoice_number="11112222", buyer_name="别的公司")
    audit(bad)
    assert history.find("11112222") is None


# ------------------------------------------------------------------ R2 缺失

def test_missing_key_field_goes_manual():
    result = audit(make_fields(amount_incl_tax=None))
    assert result.verdict == "manual"
    assert "R2" in codes(result)


# ------------------------------------------------------------------ R3 抬头

def test_wrong_buyer_name_is_rejected():
    result = audit(make_fields(buyer_name="杭州云帆网络科技有限公司"))
    assert result.verdict == "reject"
    assert "R3" in codes(result)
    assert any("第 8 条" == c["article_no"] for c in result.citations)


def test_wrong_buyer_tax_id_is_rejected():
    result = audit(make_fields(buyer_tax_id="91330100MA9Z9Z9Z9Z"))
    assert result.verdict == "reject"
    assert "R3" in codes(result)


# ------------------------------------------------------------------ R4 时效

def test_overdue_invoice_is_suspect():
    old = (date.today() - timedelta(days=45)).isoformat()
    result = audit(make_fields(invoice_date=old))
    assert result.verdict == "suspect"
    assert "R4" in codes(result)
    assert any(c["article_no"] == "第 15 条" for c in result.citations)


def test_recent_invoice_passes_deadline_check():
    recent = (date.today() - timedelta(days=3)).isoformat()
    result = audit(make_fields(invoice_date=recent))
    assert "R4" not in codes(result)


# ------------------------------------------------------------------ R5 标准

def test_over_standard_hotel_is_suspect():
    result = audit(make_fields(
        amount_excl_tax=1207.55, tax_amount=72.45, amount_incl_tax=1280.0,
        items=[InvoiceItem(name="住宿费", amount=1207.55)],
    ))
    assert result.verdict == "suspect"
    assert "R5" in codes(result)
    hit = next(h for h in result.hits if h["code"] == "R5")
    assert hit["evidence"]["diff"] == 480.0
    assert any(c["article_no"] == "第 12 条" for c in result.citations)


def test_over_standard_entertainment_is_suspect():
    result = audit(make_fields(
        category="招待",
        amount_excl_tax=2358.49, tax_amount=141.51, amount_incl_tax=2500.0,
        items=[InvoiceItem(name="餐饮服务", amount=2358.49)],
    ))
    assert "R5" in codes(result)
    assert result.verdict == "suspect"


def test_over_standard_office_is_suspect():
    result = audit(make_fields(
        category="办公",
        amount_excl_tax=5309.73, tax_amount=690.27, amount_incl_tax=6000.0, tax_rate=0.13,
        items=[InvoiceItem(name="办公耗材", amount=5309.73)],
    ))
    assert "R5" in codes(result)


def test_category_without_standard_is_skipped_not_failed():
    """交通费制度里没写上限，就该如实跳过，不能硬套一个数字。"""
    result = audit(make_fields(
        category="交通",
        amount_excl_tax=72.02, tax_amount=6.48, amount_incl_tax=78.50, tax_rate=0.09,
        items=[InvoiceItem(name="客运服务", amount=72.02)],
    ))
    assert result.verdict == "pass"
    step = next(s for s in result.trace if s["tool"] == "check_standard")
    assert step["status"] == "skip"


# ------------------------------------------------------------------ R6 明细

def test_items_sum_mismatch_is_suspect():
    result = audit(make_fields(items=[InvoiceItem(name="住宿费", amount=500.0)]))
    assert "R6" in codes(result)


# ------------------------------------------------------------------ R7 税率

def test_tax_amount_mismatch_is_suspect():
    result = audit(make_fields(tax_amount=99.99, amount_incl_tax=741.5))
    assert "R7" in codes(result)


def test_illegal_tax_rate_is_suspect():
    result = audit(make_fields(tax_rate=0.075, tax_amount=48.11, amount_incl_tax=689.62))
    assert "R7" in codes(result)


# ------------------------------------------------------------------ R8 敏感类目

def test_sensitive_item_is_suspect():
    result = audit(make_fields(
        category="招待",
        amount_excl_tax=1495.20, tax_amount=89.71, amount_incl_tax=1584.91,
        items=[InvoiceItem(name="餐饮服务", amount=1383.02), InvoiceItem(name="酒水", amount=201.89)],
    ))
    assert "R8" in codes(result)
    hit = next(h for h in result.hits if h["code"] == "R8")
    assert hit["evidence"]["matched"] == "酒水"
    assert any(c["article_no"] == "第 9 条" for c in result.citations)


# ------------------------------------------------------------------ 优先级

def test_reject_beats_suspect():
    result = audit(make_fields(
        buyer_name="别的公司",
        amount_excl_tax=1207.55, tax_amount=72.45, amount_incl_tax=1280.0,
        items=[InvoiceItem(name="住宿费", amount=1207.55)],
    ))
    assert result.verdict == "reject"
    assert {"R3", "R5"} <= set(codes(result))


def test_manual_beats_suspect():
    """机器没把握时，就不该把"存疑"当成确定结论。"""
    result = audit(
        make_fields(amount_excl_tax=1207.55, tax_amount=72.45, amount_incl_tax=1280.0,
                    items=[InvoiceItem(name="住宿费", amount=1207.55)]),
        confidence=0.55,
    )
    assert result.verdict == "manual"
    assert {"R0", "R5"} <= set(codes(result))


# ------------------------------------------------------------------ 非发票

def test_non_invoice_goes_manual_without_running_rules():
    result = audit(is_invoice=False)
    assert result.verdict == "manual"
    assert codes(result) == ["R0"]
    assert result.trace[0]["tool"] == "skip_rules"


# ------------------------------------------------------------------ 轨迹

def test_trace_statuses_are_valid_and_numbered():
    from typing import get_args

    from app.schemas import TraceStatus

    valid = set(get_args(TraceStatus))
    result = audit()
    numbers = [step["step"] for step in result.trace]
    assert numbers == list(range(1, len(numbers) + 1))
    assert all(step["status"] in valid for step in result.trace)
    assert all(step["reason"] for step in result.trace), "每一步都要写清为什么做"


def test_rule_defs_cover_all_codes_with_basis():
    defs = {rule["code"]: rule for rule in rules.rule_defs()}
    assert set(defs) == {f"R{i}" for i in range(9)}
    for rule in defs.values():
        assert rule["why"] and rule["trigger"]
    # 有依据的规则必须真的取到了条款原文，不能在页面上留空
    for code in ("R3", "R4", "R5", "R8"):
        assert defs[code]["basis_text"], code
        assert defs[code]["basis_article"]