"""test_dataset.py — 数据集一致性测试（v3：含实拍批次 real_photo）

校验维度：条目完整性 / 文件存在性 / 字段键完整性 / 金额自洽 /
类目与税率合法性 / 雷型分布 / verdict 分布 / R6 明细一致性 /
判定口径 / 增广构成 / R2 专用样例 / 号码唯一性 / 实拍批次
运行：python -m pytest backend/tests/test_dataset.py -v
"""
import json
from collections import Counter
from pathlib import Path


DATASET_DIR = Path(__file__).resolve().parent.parent / "data" / "dataset"
GT_PATH = DATASET_DIR / "ground_truth.json"

GT = json.loads(GT_PATH.read_text(encoding="utf-8"))
INVOICES = [e for e in GT if e.get("is_invoice", True)]
NON_INVOICES = [e for e in GT if not e.get("is_invoice", True)]
REAL = [e for e in GT if e.get("augment") == "real_photo"]

EXPECTED_TOTAL = 58
EXPECTED_INVOICE = 48
EXPECTED_NON_INVOICE = 10
EXPECTED_VERDICT = {"pass": 33, "suspect": 9, "reject": 3, "manual": 13}
EXPECTED_AUGMENT = {"none": 14, "noise": 10, "rotate": 8, "fold": 5,
                    "low_confidence": 1, "real_photo": 10}
EXPECTED_RULES = {"R0": 11, "R1": 1, "R2": 2, "R3": 2, "R4": 2,
                  "R5": 2, "R6": 2, "R7": 1, "R8": 2}
LEGAL_CATEGORIES = {"住宿", "餐饮", "交通", "办公", "招待", "其他"}
LEGAL_RATES = {0.01, 0.03, 0.06, 0.09, 0.13}
# 非 R7 票：类目法定税率（住宿/餐饮/办公/招待=6%，交通=9%）
EXPECTED_R7_NUMBERS = {"ds_002.png"}  # 住宿 13%，唯一允许例外
REJECT_RULES = {"R1", "R3"}
SUSPECT_RULES = {"R4", "R5", "R6", "R7", "R8"}
INVOICE_FIELD_KEYS = {"invoice_code", "invoice_number", "invoice_date",
                      "seller_name", "seller_tax_id", "buyer_name",
                      "buyer_tax_id", "amount_excl_tax", "tax_amount",
                      "amount_incl_tax", "tax_rate", "category", "items"}
AUGMENT_KEYS = {"augment", "expected_verdict", "hit_rules", "eval_date"}


def test_ground_truth_has_50_entries():
    assert len(GT) == EXPECTED_TOTAL
    assert len(INVOICES) == EXPECTED_INVOICE
    assert len(NON_INVOICES) == EXPECTED_NON_INVOICE


def test_image_files_exist():
    for e in GT:
        assert (DATASET_DIR / e["file"]).exists(), f"缺图: {e['file']}"


def test_invoice_entries_have_all_invoice_fields_keys():
    for e in INVOICES:
        missing = INVOICE_FIELD_KEYS - e.keys()
        assert not missing, f"{e['file']} 缺字段: {missing}"
        assert AUGMENT_KEYS <= e.keys(), f"{e['file']} 缺增广字段"


def test_amounts_are_consistent():
    for e in INVOICES:
        excl, tax, incl = (e["amount_excl_tax"], e["tax_amount"],
                           e["amount_incl_tax"])
        if excl is None:  # R2 缺金额样例（ds_037）
            assert e["file"] == "ds_037.png"
            continue
        assert abs(excl + tax - incl) < 0.011, f"{e['file']} 金额不自洽"
        assert e["tax_rate"] in LEGAL_RATES


def test_category_and_tax_rate_are_legal():
    for e in INVOICES:
        assert e["category"] in LEGAL_CATEGORIES, e["file"]
        if e["invoice_number"] is None:  # R2 缺号码样例
            assert e["file"] in ("ds_036.png", "ds_037.png"), e["file"]
            continue
        if e["file"] in EXPECTED_R7_NUMBERS:
            continue  # R7 票允许异常税率
        expected_rate = 0.09 if e["category"] == "交通" else 0.06
        assert e["tax_rate"] == expected_rate, f"{e['file']} 税率异常"


def test_rule_counts_match():
    rules = Counter(r for e in GT for r in e.get("hit_rules", []))
    assert dict(rules) == dict(EXPECTED_RULES), dict(rules)


def test_verdict_distribution_matches():
    vc = Counter(e["expected_verdict"] for e in GT)
    assert dict(vc) == dict(EXPECTED_VERDICT), dict(vc)


def test_r6_items_sum_mismatch_only_on_r6():
    r6_files = {e["file"] for e in GT if "R6" in e.get("hit_rules", [])}
    for e in INVOICES:
        if e.get("amount_excl_tax") is None:
            continue
        s = sum(i["amount"] for i in e["items"])
        if e["file"] in r6_files:
            assert abs(s - e["amount_excl_tax"]) > 0.011, e["file"]
        else:
            assert abs(s - e["amount_excl_tax"]) < 0.011, e["file"]


def test_verdict_policy():
    """R1/R3→reject；R4–R8→suspect；R0/R2/非发票→manual。"""
    for e in GT:
        vr, hr = e["expected_verdict"], set(e.get("hit_rules", []))
        if not e.get("is_invoice", True):
            assert vr == "manual" and hr == {"R0"}, e["file"]
        elif hr & {"R0", "R2"}:
            assert vr == "manual", e["file"]
        elif hr & REJECT_RULES:
            assert vr == "reject", e["file"]
        elif hr & SUSPECT_RULES:
            assert vr == "suspect", e["file"]
        else:
            assert vr == "pass" and not hr, e["file"]


def test_augment_composition():
    aug = Counter(e.get("augment") for e in GT)
    assert {k: v for k, v in aug.items() if k} == dict(EXPECTED_AUGMENT), dict(aug)
    assert aug[None] == EXPECTED_NON_INVOICE  # 非发票不带 augment 字段
    ni_files = {e["file"] for e in NON_INVOICES}
    assert {"non_invoice_1.jpg","non_invoice_2.jpg","ni_03.jpg","ni_04.jpg",
            "ni_05.jpg","ni_06.jpg","ni_07.jpg","ni_08.jpg","ni_09.jpg","ni_10.jpg"} <= ni_files


def test_r2_missing_fields():
    """专用 R2 样例：ds_036 缺号码；ds_037 缺金额三件套（号码保持留白现状）。"""
    e36 = next(x for x in GT if x["file"] == "ds_036.png")
    assert e36["invoice_number"] is None, "ds_036 应缺发票号码"
    assert e36["amount_excl_tax"] is not None
    assert e36["tax_amount"] is not None
    assert e36["amount_incl_tax"] is not None

    e37 = next(x for x in GT if x["file"] == "ds_037.png")
    assert e37["amount_excl_tax"] is None, "ds_037 应缺不含税金额"
    assert e37["tax_amount"] is None, "ds_037 应缺税额"
    assert e37["amount_incl_tax"] is None, "ds_037 应缺价税合计"
    assert e37["invoice_number"] is None, "ds_037 号码保持现值（留白）"

    for e in (e36, e37):
        assert e["augment"] == "none", f"{e['file']} 应为干净票渲染"
        assert e["hit_rules"] == ["R2"], e["file"]
        assert e["expected_verdict"] == "manual", e["file"]

    null_files = {e["file"] for e in INVOICES if e["invoice_number"] is None}
    assert null_files == {"ds_036.png", "ds_037.png"}, null_files


def test_invoice_numbers_are_unique():
    nums = [e["invoice_number"] for e in INVOICES if e["invoice_number"]]
    assert len(nums) == len(set(nums)), "发票号码重复"
    assert len(nums) == EXPECTED_INVOICE - 2  # ds_036/ds_037 为 null


def test_real_photo_batch():
    """实拍批次：10 张，9 pass + 1 张超标票（real_01，住宿 829.47 > 800）。"""
    assert len(REAL) == 10
    passes = [e for e in REAL if e["expected_verdict"] == "pass"]
    flags = [e for e in REAL if e["expected_verdict"] == "suspect"]
    assert len(passes) == 9 and len(flags) == 1
    f = flags[0]
    assert f["file"] == "real_01.jpg" and f["hit_rules"] == ["R5"]
    assert f["category"] == "住宿" and f["amount_incl_tax"] > 800
    # 实拍票日期均在 eval_date 前 30 天内
    from datetime import date
    asof = date.fromisoformat("2026-11-06")
    for e in REAL:
        assert (asof - date.fromisoformat(e["invoice_date"])).days <= 30
