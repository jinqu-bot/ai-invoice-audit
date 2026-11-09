"""真模型识别准确率测评（D7 之前必须做的一件事）。

**这个脚本和 eval_dataset.py 测的是两件事，别混：**

- `eval_dataset.py`：把 ground_truth 里的字段**原样**喂给规则引擎，量的是"规则判得对不对"
  （口径一致率）。它刻意绕开了识别，所以那 40/40 不代表识别准。
- 本脚本：把**图片**喂给真视觉模型，读出来的字段跟 gt 比，量的才是"识别准不准"。

之前一直说"mock 证明不了识别能力"，现在接了真模型，这个数字第一次可以量出来。
评委会问"识别准确率多少"，答案必须来自这里，不能拿 40/40 冒充。

用法（key 只放环境变量，不落盘）：

    $env:VLM_API_KEY="sk-..."
    $env:VLM_BASE_URL="https://api.deepseek.com/v1"
    $env:VLM_MODEL="deepseek-flash"
    python scripts/eval_recognition.py --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import extract  # noqa: E402

DATASET_DIR = BACKEND_DIR / "data" / "dataset"
GROUND_TRUTH = DATASET_DIR / "ground_truth.json"

# 只比"会影响结论"的字段：金额差一分、日期差一天，结论就可能翻转
NUMERIC = ("amount_excl_tax", "tax_amount", "amount_incl_tax")
TEXT = ("invoice_number", "invoice_date", "seller_name", "buyer_name", "buyer_tax_id")
FIELDS = TEXT + NUMERIC + ("tax_rate",)


def _norm_text(value: Any) -> str:
    return "".join(str(value or "").split())


def _same(field: str, got: Any, want: Any) -> bool:
    if field in NUMERIC:
        try:
            return abs(float(got or 0) - float(want or 0)) <= 0.02
        except (TypeError, ValueError):
            return False
    if field == "tax_rate":
        try:
            return abs(float(got or 0) - float(want or 0)) <= 0.005
        except (TypeError, ValueError):
            return False
    return _norm_text(got) == _norm_text(want)


async def one(entry: dict[str, Any], sem: asyncio.Semaphore) -> dict[str, Any]:
    path = DATASET_DIR / entry["file"]
    raw = path.read_bytes()
    async with sem:
        started = time.perf_counter()
        try:
            result = await extract.extract_one(raw)
            fields = result.fields
            got = {field: getattr(fields, field, None) for field in FIELDS}
            status = "ok"
            provider, model = result.provider, result.model
        except Exception as exc:  # 单张失败不能拖垮整轮
            got = {field: None for field in FIELDS}
            status = f"error: {type(exc).__name__}: {exc}"[:200]
            provider, model = "", ""
        elapsed = int((time.perf_counter() - started) * 1000)

    hits = [field for field in FIELDS if _same(field, got.get(field), entry.get(field))]
    return {
        "file": entry["file"],
        "status": status,
        "elapsed_ms": elapsed,
        "provider": provider,
        "model": model,
        "got": got,
        "hits": hits,
        "exact_all": len(hits) == len(FIELDS),
        "verdict": entry.get("expected_verdict"),
    }


async def run(entries: list[dict[str, Any]], concurrency: int) -> dict[str, Any]:
    sem = asyncio.Semaphore(concurrency)
    started = time.perf_counter()
    rows = await asyncio.gather(*(one(entry, sem) for entry in entries))
    total_ms = int((time.perf_counter() - started) * 1000)

    ok_rows = [row for row in rows if row["status"] == "ok"]
    per_field = {
        field: sum(1 for row in ok_rows if field in row["hits"]) for field in FIELDS
    }
    return {
        "count": len(rows),
        "succeeded": len(ok_rows),
        "failed": [row for row in rows if row["status"] != "ok"],
        "exact_all": sum(1 for row in ok_rows if row["exact_all"]),
        "per_field": per_field,
        "avg_ms": round(sum(row["elapsed_ms"] for row in ok_rows) / max(1, len(ok_rows))),
        "wall_ms": total_ms,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="真模型识别准确率")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 张（0=全部）")
    parser.add_argument("--concurrency", type=int, default=3, help="并发数，别太高，会被限流")
    parser.add_argument("--json", type=Path, default=None, help="把明细写成 JSON")
    args = parser.parse_args()

    entries = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    if args.limit:
        entries = entries[: args.limit]

    report = asyncio.run(run(entries, args.concurrency))

    print(f"\n=== 真模型识别：{report['count']} 张，成功 {report['succeeded']} 张 ===")
    if report["failed"]:
        print(f"失败 {len(report['failed'])} 张：")
        for row in report["failed"][:5]:
            print(f"  {row['file']}: {row['status']}")
    print(f"字段全对（{len(FIELDS)} 个字段）：{report['exact_all']}/{report['succeeded']}")
    print(f"单张平均 {report['avg_ms']}ms，整轮 {report['wall_ms']/1000:.0f}s")
    print("\n逐字段命中：")
    for field, hit in report["per_field"].items():
        base = report["succeeded"] or 1
        print(f"  {field:18s} {hit:3d}/{base}  {hit / base * 100:5.1f}%")

    print("\n没全对的样本（前 8 个）：")
    shown = 0
    for row in report["rows"]:
        if row["status"] == "ok" and not row["exact_all"] and shown < 8:
            missed = [f for f in FIELDS if f not in row["hits"]]
            detail = ", ".join(f"{f}:{row['got'].get(f)!r}" for f in missed[:3])
            print(f"  {row['file']} 缺 {missed} → {detail}")
            shown += 1

    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n明细已写入 {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
