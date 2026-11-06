"""数据集 ↔ 规则引擎对拍的回归测试（D5 补做）。

这不是"准确率测试"——它比的是**规则口径与标注口径是否一致**，不经过 OCR。
真正的识别准确率必须等真模型，这里给的任何数字都不能拿去当准确率。

用途：
1. 把"当前已知的不一致"钉死，防止悄悄变多；
2. 保证 A 端修好的口径（R7 类目税率、R8 单字）不回退；
3. 记录清楚：batch 模式下成片的 R1 是**查重能力**，不是误判。
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

# 已知且已归因的结论不一致：ds_012–ds_023 标注 pass，但开票日距基准日已超 30 天，
# 规则按第 15 条判 R4/存疑**是对的**。要么改标签，要么把日期挪进 30 天内。
# 用"子集"断言而不是"相等"：C 修好数据后这里自然变空，测试不会变成负担。
KNOWN_DATE_DRIFT = {f"ds_{index:03d}.png" for index in range(12, 24)}

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


def test_verdict_drift_is_only_the_known_date_set(independent):
    differing = {
        row["file"]
        for row in independent["rows"]
        if row["actual_verdict"] != row["expected_verdict"]
    }
    assert differing <= KNOWN_DATE_DRIFT, (
        "出现了新的结论不一致，先看是规则错还是标签错："
        f"{sorted(differing - KNOWN_DATE_DRIFT)}"
    )


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


def test_batch_mode_turns_duplicates_into_noise(entries, independent):
    """整批模式下一片 R1，是增广样本复用母票号码的结果。

    这条测试不"修复"它，而是把它锁成事实：**整批模式的结论不能当准确率**，
    否则查重能力会被误读成误判。B 看到的 13 张差异里，很大一部分就是这个。
    """
    batch = ev.run_batch(entries, AS_OF)
    batch_hits = {row["file"] for row in batch["rows"] if "R1" in row["actual_rules"]}
    assert len(batch_hits) > 5, "整批模式没查出重复号，说明增广样本号码是唯一的"
    assert batch_hits > {R1_SAMPLE}


def test_dataset_does_not_cover_r2_yet(entries):
    """把"没覆盖"变成一条会失败的断言。

    这样以后谁再想写"数据集 R1–R8 全覆盖"，测试会先拦住他。
    C 补了 R2 样例之后，这条会失败——那时把它改成正向断言即可。
    """
    covered = {rule for entry in entries for rule in (entry.get("hit_rules") or [])}
    assert "R2" not in covered, "数据集已经有 R2 样例了，请把这条测试改成正向断言"
    assert {"R1", "R3", "R4", "R5", "R6", "R7", "R8"} <= covered