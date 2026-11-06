"""数据集 ↔ 规则引擎对拍（D5 补做，给 C 改标签用的一把尺子）。

它回答一个很具体的问题：**把 ground_truth.json 里的字段原样喂给规则引擎，
结论和标注一样吗？** 这里不经过 OCR、不经过模型，只测"规则口径"，
所以它衡量的是规则与标注是否说同一件事，**不是识别准确率**。

两种模式必须分开跑，混在一起会得出错误结论：

- `independent`（独立样本）：每张票用一个"只有 3 条预置记录"的干净台账，
  互相看不见。**准确率只能用这个数**。
- `batch`（整批）：共用一个台账，审完入账。增广样本复用了母票号码，
  于是第二张起会命中 R1 重复报销——这是**查重能力测试**，不是准确率。
  B 看到的 13 张结论不同，一部分就是这两种模式混着看造成的。

用法：
    python backend/scripts/eval_dataset.py                    # 两种模式都跑
    python backend/scripts/eval_dataset.py --mode independent
    python backend/scripts/eval_dataset.py --as-of 2026-11-20
    python backend/scripts/eval_dataset.py --json _local/align.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas import ExtractedFields  # noqa: E402
from app.services import history, rules  # noqa: E402

DATASET_DIR = BACKEND_DIR / "data" / "dataset"
GROUND_TRUTH = DATASET_DIR / "ground_truth.json"


# ------------------------------------------------------------------ 台账替身

class Ledger:
    """一个可独立复位的假台账。

    真的 history 模块走数据库，一次只能有一份；对拍需要"每张票一个干净的过去"，
    所以这里做替身。规则引擎对台账只要求一个 `find(号码, 代码)`。
    """

    def __init__(self, initial: list[dict[str, Any]] | None = None) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        for row in initial if initial is not None else history._SEED:
            self.rows[row["invoice_number"]] = row

    def find(self, invoice_number: str | None, invoice_code: str | None = None):
        return self.rows.get((invoice_number or "").strip())

    def remember(self, fields: dict[str, Any], *, verdict: str, submitted_at: str = "",
                 **_: Any) -> None:
        # 与 history.remember 同一条规则：只有通过/存疑的票才入账
        number = (fields.get("invoice_number") or "").strip()
        if number and verdict in ("pass", "suspect"):
            self.rows[number] = {
                "invoice_number": number,
                "employee": "本批报销人",
                "dept": "—",
                "reimbursement_no": "BX-本批",
                "submitted_at": submitted_at or date.today().isoformat(),
            }


# ------------------------------------------------------------------ 一条样本

def to_fields(entry: dict[str, Any]) -> ExtractedFields:
    return ExtractedFields(
        invoice_code=entry.get("invoice_code") or "",
        invoice_number=entry.get("invoice_number") or "",
        invoice_date=entry.get("invoice_date") or "",
        seller_name=entry.get("seller_name") or "",
        seller_tax_id=entry.get("seller_tax_id") or "",
        buyer_name=entry.get("buyer_name") or "",
        buyer_tax_id=entry.get("buyer_tax_id") or "",
        amount_excl_tax=entry.get("amount_excl_tax") or 0.0,
        tax_amount=entry.get("tax_amount") or 0.0,
        amount_incl_tax=entry.get("amount_incl_tax") or 0.0,
        tax_rate=entry.get("tax_rate") or 0.0,
        category=entry.get("category") or "其他",
        items=entry.get("items") or [],
    )


def days_late(entry: dict[str, Any], as_of: date) -> int | None:
    raw = entry.get("invoice_date")
    if not raw:
        return None
    try:
        return (as_of - date.fromisoformat(raw)).days
    except ValueError:
        return None


def classify(entry: dict[str, Any], expected: set[str], actual: set[str],
             as_of: date, verdict_differs: bool) -> list[str]:
    """给不一致归个类，好让 C 知道该改标签还是改日期，而不是笼统地"对不上"。"""
    reasons: list[str] = []
    late = days_late(entry, as_of)
    if "R1" in actual and "R1" not in expected:
        reasons.append("ledger")          # 台账撞号：模式/号码问题，不是规则错
    if "R4" in actual and "R4" not in expected and late is not None and late > rules.DEADLINE_DAYS:
        reasons.append(f"date_within_30d({late}d)")
    if "R4" not in actual and "R4" in expected:
        reasons.append("date_expected_r4")
    if "R5" in actual and "R5" not in expected:
        reasons.append("standard")
    if "R6" in actual and "R6" not in expected:
        reasons.append("items_sum")
    if "R7" in actual and "R7" not in expected:
        reasons.append("tax_rate")
    if "R7" in expected and "R7" not in actual:
        reasons.append("tax_rate_missed")
    if "R8" in actual and "R8" not in expected:
        reasons.append("sensitive")
    if "R8" in expected and "R8" not in actual:
        reasons.append("sensitive_missed")
    if verdict_differs and not reasons:
        reasons.append("other")
    return reasons


def audit_one(entry: dict[str, Any], ledger: Ledger, as_of: date):
    confidence = 0.5 if entry.get("augment") == "low_confidence" else 0.95
    return rules.run_audit(
        to_fields(entry),
        confidence=confidence,
        is_invoice=bool(entry.get("is_invoice")),
        history=ledger,
        today=as_of,
    )


# ------------------------------------------------------------------ 两种模式

def run_independent(entries: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    rows = []
    for entry in entries:
        ledger = Ledger()          # 每张票一个干净的过去
        result = audit_one(entry, ledger, as_of)
        expected_rules = set(entry.get("hit_rules") or [])
        actual_rules = {hit["code"] for hit in result.hits}
        verdict_differs = result.verdict != entry.get("expected_verdict")
        rows.append(
            {
                "file": entry["file"],
                "as_of": as_of.isoformat(),
                "days_since_invoice": days_late(entry, as_of),
                "expected_verdict": entry.get("expected_verdict"),
                "actual_verdict": result.verdict,
                "expected_rules": sorted(expected_rules),
                "actual_rules": sorted(actual_rules),
                "reasons": classify(entry, expected_rules, actual_rules, as_of, verdict_differs),
                "headline": result.headline,
            }
        )
    return summarize(rows, "independent")


def run_batch(entries: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    ledger = Ledger()
    rows = []
    for entry in entries:
        result = audit_one(entry, ledger, as_of)
        expected_rules = set(entry.get("hit_rules") or [])
        actual_rules = {hit["code"] for hit in result.hits}
        verdict_differs = result.verdict != entry.get("expected_verdict")
        rows.append(
            {
                "file": entry["file"],
                "as_of": as_of.isoformat(),
                "expected_verdict": entry.get("expected_verdict"),
                "actual_verdict": result.verdict,
                "expected_rules": sorted(expected_rules),
                "actual_rules": sorted(actual_rules),
                "reasons": classify(entry, expected_rules, actual_rules, as_of, verdict_differs),
                "headline": result.headline,
            }
        )
        ledger.remember(
            to_fields(entry).model_dump(),
            verdict=result.verdict,
            submitted_at=f"{as_of.isoformat()} 00:00",
        )
    return summarize(rows, "batch")


def summarize(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    mismatched = [
        r for r in rows
        if r["actual_verdict"] != r["expected_verdict"] or r["actual_rules"] != r["expected_rules"]
    ]
    verdict_mismatch = [r for r in rows if r["actual_verdict"] != r["expected_verdict"]]
    rule_mismatch = [r for r in rows if r["actual_rules"] != r["expected_rules"]]
    exact = len(rows) - len(rule_mismatch)
    return {
        "mode": mode,
        "total": len(rows),
        "verdict_match": len(rows) - len(verdict_mismatch),
        "verdict_mismatch": len(verdict_mismatch),
        "rules_exact_match": exact,
        "mismatched": mismatched,
        "rows": rows,
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"\n=== {report['mode']}: {report['total']} 张 ===")
    print(f"结论一致 {report['verdict_match']}/{report['total']}"
          f"  ·  规则集合完全一致 {report['rules_exact_match']}/{report['total']}")
    if not report["mismatched"]:
        print("无不一致。")
        return
    print(f"不一致 {len(report['mismatched'])} 张：")
    for row in report["mismatched"]:
        print(
            f"  {row['file']}  {row['expected_verdict']}->{row['actual_verdict']}"
            f"  rules {row['expected_rules']}->{row['actual_rules']}"
            f"  {','.join(row['reasons'])}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="数据集与规则引擎对拍")
    parser.add_argument("--as-of", default="2026-11-06", help="评估基准日（决定 R4 是否超期）")
    parser.add_argument("--mode", choices=["independent", "batch", "both"], default="both")
    parser.add_argument("--json", default="", help="把完整结果写到这个路径")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)
    entries = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))

    reports = []
    if args.mode in ("independent", "both"):
        reports.append(run_independent(entries, as_of))
    if args.mode in ("batch", "both"):
        reports.append(run_batch(entries, as_of))

    for report in reports:
        print_report(report)

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"as_of": as_of.isoformat(), "reports": reports}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n完整结果已写入 {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())