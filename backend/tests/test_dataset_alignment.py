"""数据集 ↔ 规则引擎对拍的回归测试（D5 补做）。

这不是"准确率测试"——它比的是**规则口径与标注口径是否一致**，不经过 OCR。
真正的识别准确率必须等真模型，这里给的任何数字都不能拿去当准确率。

用途：
1. 把"当前已知的不一致"钉死，防止悄悄变多；
2. 保证 A 端修好的口径（R7 类目税率、R8 单字）不回退；
3. 验证 C 唯一化号码后整批仅命中预置 R1，保留四个未对齐的规则标签。
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import eval_dataset as ev  # noqa: E402
from app.services import rules  # noqa: E402

GROUND_TRUTH = BACKEND_DIR / "data" / "dataset" / "ground_truth.json"
AS_OF = date(2026, 11, 6)

# 数据集里唯一的"重复报销"样本：故意用了台账预置号码（演示批次那张红票）
R1_SAMPLE = "ds_003.png"


@pytest.fixture(scope="module")
def entries() -> list[dict]:
    return json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entry_map(entries) -> dict[str, dict]:
    return {entry["file"]: entry for entry in entries}


@pytest.fixture(scope="module")
def independent(entries) -> dict:
    return ev.run_independent(entries, AS_OF)


def _r5_justified(entry: dict) -> bool:
    """多出来的 R5 是不是本来就该有：超了该类目的制度上限。"""
    limit = rules.LIMITS.get(entry.get("category") or "", {}).get("limit")
    return limit is not None and (entry.get("amount_incl_tax") or 0) > limit


def _unexplained(row: dict, entry: dict) -> list[str]:
    """把每一处差异都逼到一个理由上。理由站不住的，才算真问题。"""
    reasons = row["reasons"]
    extra = set(row["actual_rules"]) - set(row["expected_rules"])
    missing = set(row["expected_rules"]) - set(row["actual_rules"])

    allowed_extra: set[str] = set()
    if any(reason.startswith("date_within_30d") for reason in reasons):
        allowed_extra.add("R4")
    if _r5_justified(entry):
        allowed_extra.add("R5")
    if row["expected_verdict"] == "manual" and row["actual_verdict"] == "manual":
        # 转人工的票，引擎会记下"为什么转人工"（R0），标注里没写是约定差异
        allowed_extra.add("R0")

    problems = [
        reason for reason in reasons
        if not reason.startswith("date_within_30d")
        and not (reason == "standard" and _r5_justified(entry))
    ]
    problems += [f"extra:{code}" for code in sorted(extra - allowed_extra)]
    # C bb0d835 标了 R2，但这两张只缺非必填 seller_tax_id；低置信度命中 R0。
    # 明确保留这个已知差异，不能把规则口径一致率写成 100%。
    if row["file"] in ("ds_036.png", "ds_037.png"):
        assert entry.get("seller_tax_id") is None
        assert "seller_tax_id" not in rules.REQUIRED_FIELDS
        assert set(row["actual_rules"]) == {"R0"}
        missing -= {"R2"}
    problems += [f"missed:{code}" for code in sorted(missing)]
    return problems


def test_c_fixed_dates_have_no_verdict_drift(independent):
    assert independent["verdict_match"] == 40


def test_every_drift_has_a_standing_explanation(independent, entry_map):
    for row in independent["rows"]:
        problems = _unexplained(row, entry_map[row["file"]])
        assert not problems, f"{row['file']} 有无法归因的差异：{problems}"


def test_hotel_with_goods_tax_rate_is_now_flagged(independent):
    """B/C 提的第 3 条：住宿开 13% 应判 R7。"""
    row = next(item for item in independent["rows"] if item["file"] == "ds_002.png")
    assert "R7" in row["actual_rules"]


def test_single_char_tobacco_item_is_now_flagged(independent):
    """B/C 提的第 2 条：明细只写一个「烟」也要抓到。"""
    row = next(item for item in independent["rows"] if item["file"] == "ds_011.png")
    assert "R8" in row["actual_rules"]


def test_only_the_designated_sample_hits_duplicate_r1(independent):
    """独立模式下应该只有唯一那张"重复报销"样本命中 R1。

    如果有第二张，要么台账没隔离干净，要么数据集里撞号了。
    """
    hit = {row["file"] for row in independent["rows"] if "R1" in row["actual_rules"]}
    assert hit == {R1_SAMPLE}, f"R1 命中集合异常：{sorted(hit)}"


def test_batch_mode_has_only_intended_duplicate(entries):
    """C 已将增广子票号码唯一化，整批只应命中预置 R1 样例。"""
    batch = ev.run_batch(entries, AS_OF)
    batch_hits = {row["file"] for row in batch["rows"] if "R1" in row["actual_rules"]}
    assert batch_hits == {R1_SAMPLE}
    assert batch["verdict_match"] == 40


def test_r2_labels_are_present_but_not_actual_coverage(entries, independent):
    labeled = {entry["file"] for entry in entries if "R2" in (entry.get("hit_rules") or [])}
    assert labeled == {"ds_036.png", "ds_037.png"}
    actual = {row["file"] for row in independent["rows"] if "R2" in row["actual_rules"]}
    assert not actual, "R2 目前仍未实际覆盖，修正样例后需同步更新此已知问题断言"
    mismatches = {row["file"] for row in independent["rows"]
                  if set(row["actual_rules"]) != set(row["expected_rules"])}
    assert mismatches == {"ds_036.png", "ds_037.png", "non_invoice_1.jpg", "non_invoice_2.jpg"}
