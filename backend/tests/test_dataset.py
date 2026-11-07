"""数据集契约测试：校验 backend/data/dataset 与 ground_truth.json 的一致性。

口径与 backend/scripts/make_dataset.py 的 docstring 保持一致：
  pass 24 / reject 3 / suspect 8 / manual 5
  R1:1 R2:2 R3:2 R4:2 R5:1 R6:2 R7:1 R8:2（另有 1 张纯 R0 低置信度票）
  R1/R3→reject，R4-R8→suspect，R0/R2/非发票→manual
  评测基准日 2026-11-06：非 R4 票开票日期在其前 30 天内，R4 票 ≤ 2026-09-20

用法：
    python -m pytest backend/tests/test_dataset.py -v
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = BACKEND_DIR / "data" / "dataset"
SAMPLES_DIR = BACKEND_DIR / "data" / "samples"
GROUND_TRUTH = DATASET_DIR / "ground_truth.json"

CATEGORIES = {"住宿", "餐饮", "交通", "办公", "招待", "其他"}
CATEGORY_RATES = {"住宿": 0.06, "餐饮": 0.06, "办公": 0.06, "交通": 0.09, "招待": 0.06, "其他": 0.06}

EXPECTED_RULE_COUNTS = {"R1": 1, "R2": 2, "R3": 2, "R4": 2, "R5": 1, "R6": 2, "R7": 1, "R8": 2}
EXPECTED_VERDICT_COUNTS = {"pass": 24, "reject": 3, "suspect": 8, "manual": 5}
RULE_VERDICT = {
    "R0": "manual",
    "R1": "reject",
    "R2": "manual",
    "R3": "reject",
    "R4": "suspect",
    "R5": "suspect",
    "R6": "suspect",
    "R7": "suspect",
    "R8": "suspect",
}
EVAL_DATE = "2026-11-06"

INVOICE_FIELD_KEYS = {
    "invoice_code",
    "invoice_number",
    "invoice_date",
    "seller_name",
    "seller_tax_id",
    "buyer_name",
    "buyer_tax_id",
    "amount_excl_tax",
    "tax_amount",
    "amount_incl_tax",
    "tax_rate",
    "category",
    "items",
}


@pytest.fixture(scope="module")
def truth() -> list[dict]:
    """ground_truth.json 可解析，返回条目列表。"""
    assert GROUND_TRUTH.exists(), f"缺少 {GROUND_TRUTH}"
    return json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def invoices(truth) -> list[dict]:
    return [t for t in truth if t.get("is_invoice")]


@pytest.fixture(scope="module")
def non_invoices(truth) -> list[dict]:
    return [t for t in truth if not t.get("is_invoice")]


# 1) 可解析、40 条
def test_ground_truth_has_40_entries(truth):
    assert isinstance(truth, list)
    assert len(truth) == 40


# 2) 每张图文件存在：发票票在 dataset/，非发票 2 张在 samples/ 存在即可
def test_image_files_exist(truth, invoices, non_invoices):
    assert len(invoices) == 38
    assert len(non_invoices) == 2
    for t in invoices:
        assert (DATASET_DIR / t["file"]).exists(), f"缺图 {t['file']}"
    for t in non_invoices:
        assert (SAMPLES_DIR / t["file"]).exists(), f"samples 缺非发票图 {t['file']}"


# 发票条目字段键名与 InvoiceFields 严格一致
def test_invoice_entries_have_all_invoice_fields_keys(invoices):
    for t in invoices:
        missing = INVOICE_FIELD_KEYS - t.keys()
        assert not missing, f"{t['file']} 缺字段 {missing}"


# 3) 金额自洽：abs(excl+tax-incl)<0.01 且 abs(excl*rate-tax)<0.05（全部发票票，
#    R7 的雷是"住宿开 13%"——税额按 13% 算是算得对的，错在税率与类目不符）
def test_amounts_are_consistent(invoices):
    for t in invoices:
        excl, tax, incl = t["amount_excl_tax"], t["tax_amount"], t["amount_incl_tax"]
        assert abs(excl + tax - incl) < 0.01, f"{t['file']} excl+tax != incl"
        assert abs(excl * t["tax_rate"] - tax) < 0.05, f"{t['file']} excl*rate 与 tax 偏差过大"


# 4) category / tax_rate 合法：非 R7 票税率必须等于类目法定税率；R7 票故意为 0.13
def test_category_and_tax_rate_are_legal(invoices):
    for t in invoices:
        assert t["category"] in CATEGORIES, f"{t['file']} 非法类目 {t['category']}"
        if "R7" in t["hit_rules"]:
            assert t["tax_rate"] == 0.13, f"{t['file']} R7 票税率应为 0.13"
            assert t["category"] == "住宿", f"{t['file']} R7 票类目应为住宿"
            assert t["amount_incl_tax"] <= 800.00, f"{t['file']} R7 票含税须 ≤800，避免误触 R5"
        else:
            assert abs(t["tax_rate"] - CATEGORY_RATES[t["category"]]) < 1e-9, (
                f"{t['file']} 税率 {t['tax_rate']} 与类目 {t['category']} 不符"
            )


# 1b) 每条都有 eval_date；非 R4 票 date > eval_date - 30 天，R4 票 ≤ 2026-09-20
def test_eval_date_and_invoice_date_window(truth, invoices):
    import datetime as dt

    eval_d = dt.date.fromisoformat(EVAL_DATE)
    for t in truth:
        assert t.get("eval_date") == EVAL_DATE, f"{t['file']} eval_date 缺失或不等于 {EVAL_DATE}"
    for t in invoices:
        d = dt.date.fromisoformat(t["invoice_date"])
        if "R4" in t["hit_rules"]:
            assert t["invoice_date"] <= "2026-09-20", f"{t['file']} R4 票日期应 ≤ 2026-09-20"
        else:
            assert eval_d - dt.timedelta(days=30) < d <= eval_d, (
                f"{t['file']} 日期 {t['invoice_date']} 不在 {EVAL_DATE} 前 30 天内"
            )


# 5b) 全部发票票 invoice_number 互不相同（R1 的重复针对历史记录，不在数据集内）
def test_invoice_numbers_are_unique(invoices):
    numbers = [t["invoice_number"] for t in invoices]
    assert len(set(numbers)) == len(numbers) == 38
    assert "66472890" in numbers, "R1 票号码应为 66472890"


# 5c) R2 票规格：seller_tax_id 为 null 且为低置信度票；其余票 seller_tax_id 非空
def test_r2_seller_tax_id_null(invoices):
    for t in invoices:
        if "R2" in t["hit_rules"]:
            assert t["seller_tax_id"] is None, f"{t['file']} R2 票 seller_tax_id 应为 null"
            assert t["augment"] == "low_confidence", f"{t['file']} R2 票应为低置信度"
        else:
            assert t["seller_tax_id"], f"{t['file']} 非 R2 票 seller_tax_id 不应为空"


# 5) 雷型计数对拍（R0 是纯低置信度票的固有路径，单独核 1 张，不计入雷型表）
def test_rule_counts_match(invoices):
    counts = Counter(r for t in invoices for r in t["hit_rules"])
    assert counts.pop("R0", 0) == 1, "纯 R0 低置信度票应为 1 张"
    assert dict(counts) == EXPECTED_RULE_COUNTS


# 6) verdict 分布对拍：pass 24 / reject 3 / suspect 8 / manual 5
def test_verdict_distribution_matches(truth):
    counts = Counter(t["expected_verdict"] for t in truth)
    assert dict(counts) == EXPECTED_VERDICT_COUNTS


# 7) R6 票 items 合计 ≠ excl；无 R6 票 items 合计 == excl
def test_r6_items_sum_mismatch_only_on_r6(invoices):
    for t in invoices:
        items_sum = round(sum(i["amount"] for i in t["items"]), 2)
        excl = round(t["amount_excl_tax"], 2)
        if "R6" in t["hit_rules"]:
            assert items_sum != excl, f"{t['file']} 标了 R6 但明细合计对得上"
        else:
            assert items_sum == excl, f"{t['file']} 无 R6 但明细合计 {items_sum} != {excl}"


# 8) 口径断言：R1/R3→reject，R4-R8→suspect，低置信度/非发票→manual
def test_verdict_policy(truth):
    for t in truth:
        if not t.get("is_invoice"):
            assert t["expected_verdict"] == "manual", f"{t['file']} 非发票应 manual"
            continue
        rules = t["hit_rules"]
        if rules:
            assert len(rules) == 1, f"{t['file']} 假定每张票至多 1 个雷"
            expect = RULE_VERDICT[rules[0]]
        elif t["augment"] == "low_confidence":
            expect = "manual"
        else:
            expect = "pass"
        assert t["expected_verdict"] == expect, (
            f"{t['file']} verdict {t['expected_verdict']} != {expect}"
        )


# 附带：增广构成对拍（12 干净 / 10 噪声 / 8 旋转 / 5 折痕 / 3 低置信度）
def test_augment_composition(invoices):
    counts = Counter(t["augment"] for t in invoices)
    assert dict(counts) == {"none": 12, "noise": 10, "rotate": 8, "fold": 5, "low_confidence": 3}
