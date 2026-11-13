"""生成一张「个人抬头 + 超期」的样例票，给**公开视频/答辩材料**用。

为什么需要它：
    演示第一幕用的是队长那张真发票，票面上是第三方（本文档用占位名「臧海涛」代替）的姓名和税号。
    现场答辩口头讲没问题，但**提交的视频/PPT 是公开材料**，把别人的姓名税号放进去不合适。

这张票解决同一件叙事，但不含任何真实个人信息：
    - 抬头是个人（触发 R3），票面上没有税号
    - 开票日期故意早于 30 天（触发 R4）
    - 金额和真票一样 4748，讲的时候可以照搬台词

用法：
    python backend/scripts/make_demo_invoice.py
产物：
    backend/data/demo/demo_personal.jpg   （可公开的样票）
    backend/data/demo/demo_personal.json  （这张票的期望字段）
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.make_dataset import build_invoice, render_invoice  # noqa: E402

OUT_DIR = BACKEND_DIR / "data" / "demo"

# 明显是编的样例名，不对应任何真人
DEMO_BUYER = "个人用户"
DEMO_AMOUNT = 4748.00
DEMO_CATEGORY = "办公"
# 距今超过 30 天——审计当天算出来就会命中 R4
DEMO_DATE = "2026-08-15"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = build_invoice(
        category=DEMO_CATEGORY,
        incl=DEMO_AMOUNT,
        date=DEMO_DATE,
        number="26222000000009847481",
        buyer_name=DEMO_BUYER,
        buyer_tax_id="",  # 个人抬头没有税号
        item_name="笔记本电脑",
    )
    image = render_invoice(fields, "demo_personal")

    jpg = OUT_DIR / "demo_personal.jpg"
    image.save(jpg, quality=92, subsampling=0)

    days = (date.today() - date.fromisoformat(fields["invoice_date"])).days
    truth = {
        "file": jpg.name,
        "note": "公开演示用样票，购买方是编的，不含任何真实个人信息",
        "expected_verdict": "reject",
        "expected_hit_rules": ["R3", "R4"],
        "days_since_invoice_on_creation": days,
        **{k: v for k, v in fields.items() if not k.startswith("_")},
    }
    (OUT_DIR / "demo_personal.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已生成 {jpg}  （{image.size[0]}×{image.size[1]}）")
    print(f"  购买方 {fields['buyer_name']}（个人，无税号）")
    print(f"  金额 {fields['amount_incl_tax']} / 类目 {fields['category']}")
    print(f"  开票日期 {fields['invoice_date']}（生成当天算 {days} 天，超 30 天 → R4）")
    print(f"  期望结论 {truth['expected_verdict']}，命中 {truth['expected_hit_rules']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())