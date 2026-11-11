"""端到端评测：真模型读图 → 规则引擎 → 结论，和 ground_truth 对拍。

**它和另外两个脚本的分工（别混）：**

- `eval_dataset.py`：把 GT 字段**原样**喂给规则引擎 → 量"规则口径"（60/60 那个数）。
  链路里没有模型，所以它**不是**识别准确率。
- `evaluate_accuracy.py`（B 的）：真模型读图 → 只比**字段**，不评 verdict（11 字段口径）。
- **本脚本**：真模型读图 → 直接跑到结论，比 **verdict 和规则集合**。
  这是唯一能回答"这套系统端到端判断准不准"的数字。

口径纪律：
- **每张票一个干净台账**（只有 3 条预置记录），互相看不见。
  否则增广样本复用母票号码，第二张起会命中 R1，测出来的是查重能力不是准确率。
- 日期用 GT 里的 `eval_date`（没有就用 --as-of），保证 R4 时效按标注当天算。
- 非发票也要跑：期望结论是 reject/manual，看它会不会被硬当成发票审。

用法（要在**有模型 key 的机器**上跑，也就是服务器）：
    cd backend && ../.venv/bin/python scripts/eval_end_to_end.py --json /root/e2e.json
    python backend/scripts/eval_end_to_end.py --limit 10 --concurrency 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import extract, rules  # noqa: E402
from eval_dataset import Ledger, classify  # noqa: E402  台账替身与归因复用对拍脚本

DATASET_DIR = BACKEND_DIR / "data" / "dataset"
GROUND_TRUTH = DATASET_DIR / "ground_truth.json"


def _as_of_for(entry: dict[str, Any], fallback: date) -> date:
    raw = entry.get("eval_date")
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            pass
    return fallback


async def _one(entry: dict[str, Any], sem: asyncio.Semaphore, fallback: date) -> dict[str, Any]:
    path = DATASET_DIR / entry["file"]
    raw = path.read_bytes()
    as_of = _as_of_for(entry, fallback)
    async with sem:
        started = time.perf_counter()
        try:
            ext = await extract.extract_one(raw)
            status = "ok"
        except Exception as exc:  # 单张失败不能拖垮整轮
            return {
                "file": entry["file"], "status": f"error: {type(exc).__name__}: {exc}"[:200],
                "expected_verdict": entry.get("expected_verdict"),
                "expected_rules": sorted(entry.get("hit_rules") or []),
                "actual_verdict": None, "actual_rules": [], "reasons": ["extract_failed"],
                "elapsed_ms": 0,
            }
        elapsed = int((time.perf_counter() - started) * 1000)

    ledger = Ledger()  # 每张票一个干净的过去
    result = rules.run_audit(
        ext.fields,
        confidence=ext.overall_confidence,
        is_invoice=ext.is_invoice,
        history=ledger,
        today=as_of,
    )
    expected_rules = set(entry.get("hit_rules") or [])
    actual_rules = {hit["code"] for hit in result.hits}
    differs = result.verdict != entry.get("expected_verdict")
    return {
        "file": entry["file"],
        "status": status,
        "as_of": as_of.isoformat(),
        "cached": bool(ext.cached),
        "elapsed_ms": elapsed,
        "confidence": round(ext.overall_confidence, 3),
        "is_invoice": ext.is_invoice,
        "expected_verdict": entry.get("expected_verdict"),
        "actual_verdict": result.verdict,
        "expected_rules": sorted(expected_rules),
        "actual_rules": sorted(actual_rules),
        "rules_match": expected_rules == actual_rules,
        "verdict_match": not differs,
        "reasons": classify(entry, expected_rules, actual_rules, as_of, differs),
        "headline": result.headline,
        "fields": {
            "buyer_name": ext.fields.buyer_name,
            "invoice_number": ext.fields.invoice_number,
            "invoice_date": ext.fields.invoice_date,
            "amount_incl_tax": ext.fields.amount_incl_tax,
        },
    }


async def _run(entries: list[dict[str, Any]], concurrency: int, fallback: date) -> dict[str, Any]:
    sem = asyncio.Semaphore(concurrency)
    started = time.perf_counter()
    rows = await asyncio.gather(*(_one(e, sem, fallback) for e in entries))
    rows = sorted(rows, key=lambda r: r["file"])
    ok = [r for r in rows if r["status"] == "ok"]
    return {
        "count": len(rows),
        "succeeded": len(ok),
        "verdict_match": sum(1 for r in ok if r["verdict_match"]),
        "rules_match": sum(1 for r in ok if r["rules_match"]),
        "cached": sum(1 for r in ok if r.get("cached")),
        "avg_ms": round(sum(r["elapsed_ms"] for r in ok) / max(1, len(ok))),
        "wall_ms": int((time.perf_counter() - started) * 1000),
        "by_expected": {
            verdict: {
                "count": sum(1 for r in ok if r["expected_verdict"] == verdict),
                "matched": sum(1 for r in ok if r["expected_verdict"] == verdict and r["verdict_match"]),
            }
            for verdict in ("pass", "suspect", "reject", "manual")
        },
        "confusion": dict(Counter(
            f"{r['expected_verdict']}→{r['actual_verdict']}" for r in ok if not r["verdict_match"]
        )),
        "rows": rows,
    }


def _markdown(report: dict[str, Any], source: str, as_of: str) -> str:
    total = report["succeeded"]
    lines = [
        "# 端到端准确率（真模型读图 → 规则 → 结论）",
        "",
        f"> 生成：{date.today().isoformat()} · 样本 {report['count']} 张 · 运行处 {source}"
        f" · 基准日 {as_of} · 每张票独立台账（不串号）",
        "",
        "**这个数字和另外两个不是一回事，引用时别混：**",
        "规则口径（`对拍结果.md`）是把 GT 字段直接喂规则，链路里没有模型；",
        "11 字段口径（`recognition-11-fields`）只比字段不评结论；",
        "**本报告是唯一跑完整条链路的数字。**",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 结论一致 | **{report['verdict_match']}/{total}** |",
        f"| 规则集合完全一致 | **{report['rules_match']}/{total}** |",
        f"| 单张平均耗时 | {report['avg_ms']} ms（其中命中缓存 {report['cached']} 张） |",
        "",
        "## 按期望结论拆开",
        "",
        "| 期望 | 张数 | 一致 |",
        "|---|---|---|",
    ]
    for verdict, stat in report["by_expected"].items():
        if stat["count"]:
            lines.append(f"| {verdict} | {stat['count']} | {stat['matched']} |")
    if report["confusion"]:
        lines += ["", "## 不一致的方向", "", "| 期望→实际 | 张数 |", "|---|---|"]
        for pair, n in sorted(report["confusion"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {pair} | {n} |")
    bad = [r for r in report["rows"] if r["status"] == "ok" and not r["verdict_match"]]
    if bad:
        lines += ["", "## 不一致明细", "", "| 票 | 期望 | 实际 | 期望规则 | 实际规则 | 归因 |", "|---|---|---|---|---|---|"]
        for r in bad:
            lines.append(
                f"| {r['file']} | {r['expected_verdict']} | {r['actual_verdict']} | "
                f"{','.join(r['expected_rules']) or '—'} | {','.join(r['actual_rules']) or '—'} | "
                f"{','.join(r['reasons']) or '—'} |"
            )
    failed = [r for r in report["rows"] if r["status"] != "ok"]
    if failed:
        lines += ["", "## 抽取失败", ""] + [f"- {r['file']}：{r['status']}" for r in failed]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="端到端准确率（识别 → 规则 → 结论）")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--as-of", default="2026-11-06", help="GT 没写 eval_date 时的基准日")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--md", type=Path, default=None)
    args = parser.parse_args()

    entries = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    if args.limit:
        entries = entries[: args.limit]
    fallback = date.fromisoformat(args.as_of)

    report = asyncio.run(_run(entries, args.concurrency, fallback))
    total = report["succeeded"]
    print(f"\n=== 端到端：{report['count']} 张，成功 {total} 张，整轮 {report['wall_ms']/1000:.0f}s ===")
    print(f"结论一致 {report['verdict_match']}/{total}   规则集合一致 {report['rules_match']}/{total}")
    print(f"单张平均 {report['avg_ms']}ms（缓存命中 {report['cached']} 张）")
    for verdict, stat in report["by_expected"].items():
        if stat["count"]:
            print(f"  期望 {verdict:7s} {stat['matched']}/{stat['count']}")
    if report["confusion"]:
        print("不一致方向：", report["confusion"])
    for row in report["rows"]:
        if row["status"] == "ok" and not row["verdict_match"]:
            print(f"  ✗ {row['file']}: {row['expected_verdict']}→{row['actual_verdict']} "
                  f"规则 {','.join(row['expected_rules']) or '—'} → {','.join(row['actual_rules']) or '—'}"
                  f"  ({','.join(row['reasons']) or '—'})")

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"明细：{args.json}")
    if args.md:
        args.md.write_text(_markdown(report, "服务器（openai-compat）", args.as_of), encoding="utf-8")
        print(f"报告：{args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
