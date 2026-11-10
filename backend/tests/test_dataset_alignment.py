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
    problems += [f"missed:{code}" for code in sorted(missing)]
    return problems


def test_c_fixed_dates_have_no_verdict_drift(independent, entries):
    """全数据集结论零漂移；样本数量跟随 GT，不能漏评或接受空集。"""
    assert independent["total"] == len(entries) > 0
    assert independent["verdict_match"] == independent["total"]


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


def test_batch_mode_no_longer_has_number_collisions(entries, independent):
    """整批模式曾经一片 R1，是增广样本复用母票号码造成的假噪声。

    C 把 38 票号码唯一化之后，这个噪声消失了：整批模式只剩那张"真重复"样本命中 R1，
    而且两套模式的结论完全一致。这条测试锁住这个前提——
    将来谁再让号码重复，整批模式会重新变脏，这里会先红。
    """
    batch = ev.run_batch(entries, AS_OF)
    batch_hits = {row["file"] for row in batch["rows"] if "R1" in row["actual_rules"]}
    assert batch_hits == {R1_SAMPLE}, f"整批模式出现了多余的重号命中：{sorted(batch_hits)}"
    assert batch["verdict_match"] == batch["total"], "整批模式还有判错的票"
    assert batch["rules_exact_match"] == batch["total"], (
        f"整批模式还有规则对不上的票：{[r['file'] for r in batch['rows'] if r['expected_rules'] != r['actual_rules']]}"
    )


def test_dataset_covers_r2_with_normal_confidence(entries, independent):
    """C 补的两张 R2 样例必须"字段缺、把握正常"，否则会退化成 R0。

    R0 和 R2 都是转人工，但理由不同：R0 是"模型自己没把握"，
    R2 是"字段确实没读到"。样本如果靠压低置信度来制造 R2，就测不出真正的缺字段路径。
    """
    covered = {rule for entry in entries for rule in (entry.get("hit_rules") or [])}
    assert {"R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"} <= covered, (
        f"数据集还没覆盖到全部规则，缺：{sorted({'R0','R1','R2','R3','R4','R5','R6','R7','R8'} - covered)}"
    )

    r2_files = {entry["file"] for entry in entries if "R2" in (entry.get("hit_rules") or [])}
    assert len(r2_files) >= 2, f"R2 样例不足两张：{sorted(r2_files)}"

    for row in independent["rows"]:
        if row["file"] in r2_files:
            assert "R2" in row["actual_rules"], f"{row['file']} 没命中 R2"
            assert "R0" not in row["actual_rules"], (
                f"{row['file']} 同时命中了 R0——说明它是靠压低置信度凑出来的 R2，不是真的缺字段"
            )
