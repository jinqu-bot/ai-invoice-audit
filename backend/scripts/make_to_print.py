"""生成 10 张干净票（打印/实拍测试用）到 backend/data/to_print/。

复用 make_dataset 的 render 链路与 truth_entry 格式：
  - 随机合法字段，日期 2026-10-10 ~ 2026-11-05（build_invoice 默认窗口）
  - 金额自洽 excl + tax = incl，税率按类目法定值
  - 不带任何雷：augment="none"、hit_rules=[]、expected_verdict="pass"
  - 图片缩放到 800x1100 PNG

用法：
    python backend/scripts/make_to_print.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_dataset import build_invoice, render_invoice, rng, truth_entry  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "to_print"
TARGET_SIZE = (800, 1100)

# 10 张干净票的类目与价税合计区间
SPECS = [
    ("住宿", (420.0, 880.0)),
    ("住宿", (420.0, 880.0)),
    ("住宿", (420.0, 880.0)),
    ("餐饮", (68.0, 360.0)),
    ("餐饮", (68.0, 360.0)),
    ("餐饮", (68.0, 360.0)),
    ("交通", (32.0, 180.0)),
    ("交通", (32.0, 180.0)),
    ("办公", (99.0, 760.0)),
    ("办公", (99.0, 760.0)),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    truth = []
    for i, (category, (lo, hi)) in enumerate(SPECS, start=1):
        file = f"print_{i:02d}.png"
        fields = build_invoice(category=category, incl=round(rng.uniform(lo, hi), 2))
        img = render_invoice(fields, file).resize(TARGET_SIZE, Image.LANCZOS)
        img.save(OUT_DIR / file, format="PNG", optimize=True)
        truth.append(truth_entry(file, fields, "none", []))
        print(f"generated {file}  {fields['category']}  ¥{fields['amount_incl_tax']:.2f}  {fields['invoice_date']}")

    out_json = OUT_DIR / "to_print_ground_truth.json"
    out_json.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ground truth -> {out_json}")

    # 自查：10 张、金额自洽、税率合法、号码唯一
    assert len(truth) == 10
    assert len({t["invoice_number"] for t in truth}) == 10
    for t in truth:
        assert abs(t["amount_excl_tax"] + t["tax_amount"] - t["amount_incl_tax"]) < 0.01
        assert abs(t["amount_excl_tax"] * t["tax_rate"] - t["tax_amount"]) < 0.05
        assert t["expected_verdict"] == "pass" and t["hit_rules"] == []
        assert "2026-10-10" <= t["invoice_date"] <= "2026-11-05"
        img = Image.open(OUT_DIR / t["file"])
        assert img.size == TARGET_SIZE, f"{t['file']} 尺寸 {img.size}"
    print("自查全部通过 ✓")


if __name__ == "__main__":
    main()
