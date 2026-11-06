"""生成正式评测数据集（40 张）到 backend/data/dataset/。

不修改 make_samples.py，直接复用其中的 render() 画发票底图。

构成（共 40 张）：
  - 12 张干净票（随机合法字段，金额自洽 excl + tax = incl）
  - 23 张增广票（10 噪声 / 8 旋转 / 5 折痕，基于干净票，要素与母票相同）
  - 埋雷票（分布于干净/增广批次，母子同雷）：
      R1 重复 1 张（发票号 66472890）
      R3 抬头错 2 张
      R4 超期 2 张（开票日期 ≤ 2026-09-20）
      R5 超标 1 张（住宿 1280）
      R6 明细不符 2 张（明细合计 ≠ 不含税金额）
      R7 税率异常 1 张（住宿 0.13）
      R8 敏感类目 2 张（项目含 "酒水" / "烟"）
  - 3 张低置信度（号码区 + 价税合计区重度像素化）→ manual
  - 2 张非发票（复制 samples/non_invoice_1.jpg、non_invoice_2.jpg）→ manual

税率口径：住宿/餐饮/办公 = 0.06，交通 = 0.09，招待/其他按服务 0.06。

期望结论口径（与规则引擎等级对齐，评测时以 hit_rules 为准）：
  pass    无雷票（干净票及其增广）
  reject  R1 / R3
  suspect R4 / R5 / R6 / R7 / R8
  manual  低置信度票、非发票

用法：
    python backend/scripts/make_dataset.py
输出：
    backend/data/dataset/ds_001.png ... ds_038.png
    backend/data/dataset/non_invoice_1.jpg / non_invoice_2.jpg
    backend/data/dataset/ground_truth.json
"""

from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_samples import render  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "dataset"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"

SEED = 20261106
rng = random.Random(SEED)

# 与 make_samples.py 保持一致的购买方（正确抬头）
BUYER_NAME = "杭州云帆科技有限公司"
BUYER_TAX_ID = "91330100MA2A1B2C3D"

TAX_RATES = {"住宿": 0.06, "餐饮": 0.06, "办公": 0.06, "交通": 0.09, "招待": 0.06, "其他": 0.06}

RULE_VERDICT = {
    "R1": "reject",
    "R3": "reject",
    "R4": "suspect",
    "R5": "suspect",
    "R6": "suspect",
    "R7": "suspect",
    "R8": "suspect",
}

# 每种雷型应命中的张数（自查用）
EXPECTED_RULE_COUNTS = {"R1": 1, "R3": 2, "R4": 2, "R5": 1, "R6": 2, "R7": 1, "R8": 2}
EXPECTED_AUGMENT_COUNTS = {"none": 12, "noise": 10, "rotate": 8, "fold": 5, "low_confidence": 3}

SELLERS = {
    "住宿": [("杭州西溪宾馆有限公司", "91330106MA2K7X1A2B"), ("宁波东港大酒店有限公司", "91330203MA2H5T8Q1C")],
    "餐饮": [("杭州鲜味餐饮管理有限公司", "91330106MA2K7X2C3D"), ("上海老正兴菜馆有限公司", "91310101MA1F3P6D8E")],
    "交通": [("滴滴出行科技有限公司", "91110108MA0KX3E4F"), ("上海强生出租汽车有限公司", "91310106MA1G2H9J5K")],
    "办公": [("杭州得力办公用品有限公司", "91330109MA2B4C6D8E"), ("北京晨光文具销售有限公司", "91110105MA1C7D2E9F")],
    "招待": [("杭州湖畔居茶楼有限公司", "91330103MA2K9L1M3N"), ("杭州醉白楼餐饮有限公司", "91330105MA2K8N4P6Q")],
    "其他": [("杭州印天下图文制作有限公司", "91330108MA2M2Q4R6S")],
}

CATEGORY_ITEMS = {
    "住宿": "住宿服务",
    "餐饮": "餐饮服务",
    "交通": "客运服务",
    "办公": "办公用品",
    "招待": "招待费",
    "其他": "图文制作费",
}

PAYEES = ["李芳", "陈晨", "孙悦", "刘畅", "周敏"]
CHECKERS = ["王强", "刘洋", "周涛", "吴磊", "郑爽"]
DRAWERS = ["张敏", "赵磊", "吴迪", "冯远", "蒋欣"]


# ---------------------------------------------------------------- 工具


def rmb_upper(amount: float) -> str:
    """金额转人民币大写，例如 680.0 -> 陆佰捌拾圆整。"""
    units = "零壹贰叁肆伍陆柒捌玖"
    int_units = ["", "拾", "佰", "仟"]
    group_units = ["", "万", "亿"]

    cents = round(amount * 100)
    integer, fraction = divmod(cents, 100)
    jiao, fen = divmod(fraction, 10)

    if integer == 0:
        int_part = ""
    else:
        groups = []
        while integer > 0:
            groups.append(integer % 10000)
            integer //= 10000
        parts = []
        for gi in range(len(groups) - 1, -1, -1):
            g = groups[gi]
            if g == 0:
                if parts and not parts[-1].endswith("零"):
                    parts.append("零")
                continue
            digits = f"{g:04d}" if gi < len(groups) - 1 else str(g)
            seg = ""
            for i, ch in enumerate(digits):
                d = int(ch)
                if d == 0:
                    if seg and not seg.endswith("零"):
                        seg += "零"
                else:
                    seg += units[d] + int_units[len(digits) - 1 - i]
            seg = seg.rstrip("零")
            parts.append(seg + group_units[gi])
        int_part = "".join(parts).strip("零") + "圆"

    if jiao == 0 and fen == 0:
        return int_part + "整"
    frac_part = ""
    if jiao:
        frac_part += units[jiao] + "角"
    elif integer and fen:
        frac_part += "零"
    if fen:
        frac_part += units[fen] + "分"
    return int_part + frac_part


def rand_tax_id() -> str:
    prefix = rng.choice(["91330106", "91330109", "91110108", "91310101", "91330203"])
    body = "".join(rng.choice("0123456789ABCDEFGHJKLMNPQRTUWXY") for _ in range(10))
    return prefix + body


def rand_invoice_code() -> str:
    return "03300" + "".join(rng.choice("0123456789") for _ in range(7))


def rand_date(start: tuple[int, int, int], end: tuple[int, int, int]) -> str:
    import datetime as dt

    a = dt.date(*start).toordinal()
    b = dt.date(*end).toordinal()
    return dt.date.fromordinal(rng.randint(a, b)).isoformat()


def cn_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{y}年{m}月{d}日"


# ---------------------------------------------------------------- 版式坐标
# 以下坐标与 make_samples.render 的固定版式严格对应（宽 860 高 1120）。


def layout(n_items: int) -> dict[str, tuple[int, int, int, int]]:
    y_items_end = 460 + 40 * n_items  # render 中明细循环结束后的 y
    y_incl = y_items_end + 76         # 价税合计行
    y_seller = y_incl + 56            # 销售方名称行
    return {
        "number": (515, 105, 840, 142),                          # 发票号码（右上）
        "incl": (50, y_incl - 10, 840, y_incl + 36),             # 价税合计（大写+小写）
        "amount_band": (48, y_items_end + 8, 812, y_incl + 34),  # 合计+价税合计整带
        "buyer_tax_band": (48, 212, 812, 252),                   # 购买方税号
        "seller_tax_band": (48, y_seller + 24, 812, y_seller + 64),  # 销售方税号
    }


# ---------------------------------------------------------------- 增广


def add_noise(img: Image.Image) -> Image.Image:
    """噪点 + 亮度随机 0.85~1.15。"""
    out = ImageEnhance.Brightness(img).enhance(rng.uniform(0.85, 1.15))
    noise = Image.effect_noise(out.size, rng.uniform(20, 34)).convert("L")
    # 噪点重新中心化（均值拉回 128），再低比例混入
    noise = noise.point(lambda p: max(0, min(255, 128 + (p - 128) // 3)))
    out = Image.blend(out, Image.merge("RGB", (noise, noise, noise)), rng.uniform(0.10, 0.18))
    return out


def rotate(img: Image.Image) -> Image.Image:
    """±3°~±8° 旋转，白底填充。"""
    angle = rng.uniform(3.0, 8.0) * rng.choice([1, -1])
    return img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))


def add_fold(img: Image.Image, boxes: dict[str, tuple[int, int, int, int]]) -> Image.Image:
    """半透明白色横带（折痕），压在金额区或税号区。"""
    target = rng.choice(["amount_band", "buyer_tax_band", "seller_tax_band"])
    x0, y0, x1, y1 = boxes[target]
    band_h = rng.randint(34, min(56, y1 - y0))
    y_top = rng.randint(y0, y1 - band_h)

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    alpha = rng.randint(120, 165)
    d.rectangle([x0, y_top, x1, y_top + band_h], fill=(255, 255, 255, alpha))
    # 折痕上下边缘的灰线，模拟纸痕
    d.line([x0, y_top, x1, y_top], fill=(180, 184, 192, 110), width=2)
    d.line([x0, y_top + band_h, x1, y_top + band_h], fill=(200, 204, 210, 90), width=1)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def blur_region(
    img: Image.Image,
    boxes: list[tuple[int, int, int, int]],
    block: int = 10,
) -> Image.Image:
    """把指定区域像素化（马赛克）。"""
    out = img.copy()
    for x0, y0, x1, y1 in boxes:
        region = out.crop((x0, y0, x1, y1))
        w, h = region.size
        small = region.resize((max(1, w // block), max(1, h // block)), Image.NEAREST)
        out.paste(small.resize((w, h), Image.NEAREST), (x0, y0))
    return out


# ---------------------------------------------------------------- 造票

USED_NUMBERS: set[str] = set()


def rand_number() -> str:
    while True:
        n = "".join(rng.choice("0123456789") for _ in range(8))
        if n not in USED_NUMBERS:
            USED_NUMBERS.add(n)
            return n


def build_invoice(
    *,
    category: str,
    incl: float,
    rate: float | None = None,
    date: str | None = None,
    number: str | None = None,
    buyer_name: str = BUYER_NAME,
    item_name: str | None = None,
    bad_items: list[tuple[str, float]] | None = None,
    seller_idx: int = 0,
) -> dict:
    """生成一张票的字段（excl/tax 由 incl 和税率反推，保证 excl + tax = incl）。"""
    rate = TAX_RATES[category] if rate is None else rate
    excl = round(incl / (1 + rate), 2)
    tax = round(incl - excl, 2)
    seller_name, seller_tax_id = SELLERS[category][seller_idx % len(SELLERS[category])]

    if bad_items is not None:
        # R6：明细合计故意对不上 excl
        items = list(bad_items)
    else:
        items = [(item_name or CATEGORY_ITEMS[category], excl)]

    truth_items = [{"name": n, "amount": round(a, 2)} for n, a in items]
    render_items = []
    tax_left = tax
    for i, (n, a) in enumerate(items):
        if i < len(items) - 1:
            t = round(a * rate, 2)
            tax_left = round(tax_left - t, 2)
        else:
            t = tax_left
        render_items.append((n, f"{a:.2f}", f"{int(rate * 100)}%", f"{t:.2f}"))

    return {
        "invoice_code": rand_invoice_code(),
        "invoice_number": number or rand_number(),
        "invoice_date": date or rand_date((2026, 9, 21), (2026, 11, 5)),
        "seller_name": seller_name,
        "seller_tax_id": seller_tax_id,
        "buyer_name": buyer_name,
        "buyer_tax_id": BUYER_TAX_ID,
        "amount_excl_tax": excl,
        "tax_amount": tax,
        "amount_incl_tax": round(incl, 2),
        "tax_rate": rate,
        "category": category,
        "items": truth_items,
        "_render_items": render_items,
    }


def render_invoice(fields: dict, file: str) -> Image.Image:
    data = {
        "file": file,
        "title": "增值税电子普通发票",
        "invoice_code": fields["invoice_code"],
        "invoice_number": fields["invoice_number"],
        "invoice_date": cn_date(fields["invoice_date"]),
        "buyer_name": fields["buyer_name"],
        "buyer_tax_id": fields["buyer_tax_id"],
        "seller_name": fields["seller_name"],
        "seller_tax_id": fields["seller_tax_id"],
        "items": fields["_render_items"],
        "excl": f"{fields['amount_excl_tax']:.2f}",
        "tax": f"{fields['tax_amount']:.2f}",
        "incl": f"{fields['amount_incl_tax']:.2f}",
        "incl_cn": rmb_upper(fields["amount_incl_tax"]),
        "category": fields["category"],
        "payee": rng.choice(PAYEES),
        "checker": rng.choice(CHECKERS),
        "drawer": rng.choice(DRAWERS),
    }
    return render(data)


# ---------------------------------------------------------------- 数据集编排
#
# 12 个母票谱系；增广票要素与母票完全一致，因此母票带雷则子票同雷。
# 每种雷型命中的"张数" = 该谱系（1 母 + 子）总数，正好对上 EXPECTED_RULE_COUNTS。


def build_plan() -> list[dict]:
    plan: list[dict] = []

    def parent(idx: int, mines: list[str], **kw) -> dict:
        return {"idx": idx, "fields": build_invoice(**kw), "mines": mines, "children": []}

    # L1  R5 超标：住宿 1280
    plan.append(parent(1, ["R5"], category="住宿", incl=1280.00))
    # L2  R7 税率异常：住宿 0.13
    plan.append(parent(2, ["R7"], category="住宿", incl=904.00, rate=0.13, seller_idx=1))
    # L3  R1 重复：发票号 66472890
    USED_NUMBERS.add("66472890")
    plan.append(parent(3, ["R1"], category="办公", incl=356.00, number="66472890"))
    # L4  R3 抬头错（母 + 1 噪声子 = 2 张）
    plan.append(parent(4, ["R3"], category="餐饮", incl=512.00, buyer_name="杭州云帆科技有限公可"))
    # L5  R4 超期（母 + 1 旋转子 = 2 张），日期 ≤ 2026-09-20
    plan.append(parent(5, ["R4"], category="交通", incl=186.50, date="2026-08-18"))
    # L6  R6 明细不符（母 + 1 折痕子 = 2 张）：明细合计 420 ≠ 不含税 471.70
    plan.append(
        parent(
            6, ["R6"], category="办公", incl=500.00,
            bad_items=[("办公用品", 300.00), ("打印纸", 120.00)],
        )
    )
    # L7  R8 敏感类目：项目含"酒水"
    plan.append(parent(7, ["R8"], category="招待", incl=968.00, item_name="酒水"))
    # L8  R8 敏感类目：项目含"烟"
    plan.append(parent(8, ["R8"], category="餐饮", incl=268.00, item_name="烟", seller_idx=1))
    # L9-L12  干净谱系，吸收剩余 20 张子票
    plan.append(parent(9, [], category="住宿", incl=rng.choice([486.0, 552.0, 618.0])))
    plan.append(parent(10, [], category="餐饮", incl=rng.choice([128.0, 236.0, 328.0]), seller_idx=1))
    plan.append(parent(11, [], category="交通", incl=rng.choice([46.8, 89.5, 152.3]), seller_idx=1))
    plan.append(parent(12, [], category="办公", incl=rng.choice([199.0, 459.0, 760.0]), seller_idx=1))

    # 子票分配：噪声 10 / 旋转 8 / 折痕 5
    child_specs = {
        4: ["noise"],
        5: ["rotate"],
        6: ["fold"],
        9: ["noise", "noise", "noise", "rotate", "rotate"],
        10: ["noise", "noise", "noise", "rotate", "rotate"],
        11: ["noise", "noise", "noise", "rotate", "rotate"],
        12: ["rotate", "fold", "fold", "fold", "fold"],
    }
    for p in plan:
        p["children"] = list(child_specs.get(p["idx"], []))

    counts = {"noise": 0, "rotate": 0, "fold": 0}
    for p in plan:
        for c in p["children"]:
            counts[c] += 1
    assert counts == {"noise": 10, "rotate": 8, "fold": 5}, counts
    return plan


def truth_entry(file: str, fields: dict, augment: str, mines: list[str]) -> dict:
    return {
        "file": file,
        "is_invoice": True,
        # ---- 以下键名与 backend/app/schemas.py 的 InvoiceFields 严格一致 ----
        "invoice_code": fields["invoice_code"],
        "invoice_number": fields["invoice_number"],
        "invoice_date": fields["invoice_date"],
        "seller_name": fields["seller_name"],
        "seller_tax_id": fields["seller_tax_id"],
        "buyer_name": fields["buyer_name"],
        "buyer_tax_id": fields["buyer_tax_id"],
        "amount_excl_tax": fields["amount_excl_tax"],
        "tax_amount": fields["tax_amount"],
        "amount_incl_tax": fields["amount_incl_tax"],
        "tax_rate": fields["tax_rate"],
        "category": fields["category"],
        "items": fields["items"],
        # ---- 评测元信息 ----
        "augment": augment,
        "expected_verdict": RULE_VERDICT[mines[0]] if mines else ("manual" if augment == "low_confidence" else "pass"),
        "hit_rules": list(mines),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # 清掉旧的生成物，保证数量自查不受残留文件干扰
    for old in OUT_DIR.glob("*"):
        old.unlink()

    truth: list[dict] = []
    seq = 0

    def save(img: Image.Image, file: str) -> None:
        img.save(OUT_DIR / file, format="PNG", optimize=True)
        print(f"generated {file}")

    # ---- 12 张干净母票 + 23 张增广子票 ----
    for p in build_plan():
        seq += 1
        file = f"ds_{seq:03d}.png"
        img = render_invoice(p["fields"], file)
        save(img, file)
        truth.append(truth_entry(file, p["fields"], "none", p["mines"]))

        boxes = layout(len(p["fields"]["items"]))
        for aug in p["children"]:
            seq += 1
            cfile = f"ds_{seq:03d}.png"
            if aug == "noise":
                cimg = add_noise(img)
            elif aug == "rotate":
                cimg = rotate(img)
            else:
                cimg = add_fold(img, boxes)
            save(cimg, cfile)
            truth.append(truth_entry(cfile, p["fields"], aug, p["mines"]))

    # ---- 3 张低置信度：号码区 + 价税合计区重模糊 ----
    low_conf_specs = [
        {"category": "住宿", "incl": 736.00},
        {"category": "交通", "incl": 118.30, "seller_idx": 1},
        {"category": "办公", "incl": 265.00, "seller_idx": 1},
    ]
    for spec in low_conf_specs:
        seq += 1
        file = f"ds_{seq:03d}.png"
        fields = build_invoice(**spec)
        img = render_invoice(fields, file)
        boxes = layout(len(fields["items"]))
        img = blur_region(img, [boxes["number"], boxes["incl"]], block=rng.randint(16, 20))
        save(img, file)
        truth.append(truth_entry(file, fields, "low_confidence", []))

    # ---- 2 张非发票 ----
    for name in ("non_invoice_1.jpg", "non_invoice_2.jpg"):
        shutil.copy2(SAMPLES_DIR / name, OUT_DIR / name)
        print(f"copied    {name}")
        truth.append({"file": name, "is_invoice": False, "expected_verdict": "manual"})

    (OUT_DIR / "ground_truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"ground truth -> {OUT_DIR / 'ground_truth.json'}")

    self_check(truth)


# ---------------------------------------------------------------- 自查


def self_check(truth: list[dict]) -> None:
    from collections import Counter

    errors: list[str] = []

    # 1) 40 张图齐（38 生成 + 2 复制），且与 ground_truth 一一对应
    images = [p for p in OUT_DIR.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    if len(images) != 40:
        errors.append(f"图片数量 {len(images)} != 40")
    truth_files = {t["file"] for t in truth}
    disk_files = {p.name for p in images}
    if truth_files != disk_files:
        errors.append(f"ground_truth 与磁盘文件不一致: {sorted(truth_files ^ disk_files)}")

    invoices = [t for t in truth if t.get("is_invoice")]
    non_invoices = [t for t in truth if not t.get("is_invoice")]

    # 2) 金额自洽：excl + tax = incl（全部发票票）
    for t in invoices:
        if round(t["amount_excl_tax"] + t["tax_amount"], 2) != round(t["amount_incl_tax"], 2):
            errors.append(
                f"{t['file']} 金额不自洽: "
                f"{t['amount_excl_tax']} + {t['tax_amount']} != {t['amount_incl_tax']}"
            )

    # 3) 非 R7 票税率与类目匹配
    for t in invoices:
        if "R7" not in t["hit_rules"]:
            expect = TAX_RATES[t["category"]]
            if abs(t["tax_rate"] - expect) > 1e-9:
                errors.append(f"{t['file']} 税率 {t['tax_rate']} 与类目 {t['category']} 不符")

    # 4) 构成数量
    aug_counts = Counter(t["augment"] for t in invoices)
    if dict(aug_counts) != EXPECTED_AUGMENT_COUNTS:
        errors.append(f"增广构成 {dict(aug_counts)} != {EXPECTED_AUGMENT_COUNTS}")
    if len(non_invoices) != 2:
        errors.append(f"非发票数量 {len(non_invoices)} != 2")

    # 5) 每种雷型数量
    rule_counts: Counter = Counter()
    for t in invoices:
        for r in t["hit_rules"]:
            rule_counts[r] += 1
    if dict(rule_counts) != EXPECTED_RULE_COUNTS:
        errors.append(f"雷型数量 {dict(rule_counts)} != {EXPECTED_RULE_COUNTS}")

    # 6) 雷的具体规格
    for t in invoices:
        if "R1" in t["hit_rules"] and t["invoice_number"] != "66472890":
            errors.append(f"{t['file']} R1 但发票号 {t['invoice_number']} != 66472890")
        if "R4" in t["hit_rules"] and t["invoice_date"] > "2026-09-20":
            errors.append(f"{t['file']} R4 但日期 {t['invoice_date']} 未超期")
        if "R5" in t["hit_rules"] and not (t["category"] == "住宿" and t["amount_incl_tax"] == 1280.00):
            errors.append(f"{t['file']} R5 规格不符")
        if "R6" in t["hit_rules"]:
            s = round(sum(i["amount"] for i in t["items"]), 2)
            if s == round(t["amount_excl_tax"], 2):
                errors.append(f"{t['file']} R6 但明细合计反而对得上")
        if "R7" in t["hit_rules"] and not (t["category"] == "住宿" and t["tax_rate"] == 0.13):
            errors.append(f"{t['file']} R7 规格不符")
        if "R8" in t["hit_rules"]:
            text = " ".join(i["name"] for i in t["items"])
            if "酒水" not in text and "烟" not in text:
                errors.append(f"{t['file']} R8 但明细里没有 酒水/烟")

    # 7) verdict 与雷型映射一致
    for t in invoices:
        expect = (
            RULE_VERDICT[t["hit_rules"][0]]
            if t["hit_rules"]
            else ("manual" if t["augment"] == "low_confidence" else "pass")
        )
        if t["expected_verdict"] != expect:
            errors.append(f"{t['file']} verdict {t['expected_verdict']} != {expect}")
    for t in non_invoices:
        if t["expected_verdict"] != "manual":
            errors.append(f"{t['file']} 非发票 verdict 应为 manual")

    print("\n================ 自查 ================")
    print(f"图片总数        : {len(images)} (发票 {len(invoices)}, 非发票 {len(non_invoices)})")
    print(f"增广构成        : {dict(aug_counts)}")
    print(f"雷型分布        : {dict(rule_counts)}")
    if errors:
        print(f"\n自查失败 {len(errors)} 项：")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    print("自查全部通过 ✓")


if __name__ == "__main__":
    main()
