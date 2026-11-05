"""生成样例发票图片（测试用，不是 C 的正式数据集）。

作用只有一个：让抽取链路在没有真实发票的情况下也能被端到端验证。
C 的正式生成器（40 张、带噪声/旋转/折痕/低光照）在 D3 做，那个才是评测用的。

用法：
    python backend/scripts/make_samples.py
输出：
    backend/data/samples/inv_001.png ... inv_003.png
    backend/data/samples/ground_truth.json   ← 标准答案，D11 评测直接复用
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"

FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\msyh.ttc", 0),
    (r"C:\Windows\Fonts\msyhl.ttc", 0),
    (r"C:\Windows\Fonts\simsun.ttc", 0),
    (r"C:\Windows\Fonts\simhei.ttf", 0),
]

SAMPLES = [
    {
        "file": "inv_001.png",
        "title": "增值税电子普通发票",
        "invoice_code": "033002200111",
        "invoice_number": "24815631",
        "invoice_date": "2026年11月01日",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "seller_name": "杭州西溪宾馆有限公司",
        "seller_tax_id": "91330106MA2K7X1A2B",
        "items": [("住宿服务", "641.51", "6%", "38.49")],
        "excl": "641.51",
        "tax": "38.49",
        "incl": "680.00",
        "incl_cn": "陆佰捌拾圆整",
        "category": "住宿",
        "payee": "李芳",
        "checker": "王强",
        "drawer": "张敏",
    },
    {
        "file": "inv_002.png",
        "title": "增值税电子普通发票",
        "invoice_code": "033002200112",
        "invoice_number": "31027744",
        "invoice_date": "2026年10月30日",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "seller_name": "杭州鲜味餐饮管理有限公司",
        "seller_tax_id": "91330106MA2K7X2C3D",
        "items": [("餐饮服务", "337.74", "6%", "20.26")],
        "excl": "337.74",
        "tax": "20.26",
        "incl": "358.00",
        "incl_cn": "叁佰伍拾捌圆整",
        "category": "招待",
        "payee": "陈晨",
        "checker": "刘洋",
        "drawer": "赵磊",
    },
    {
        "file": "inv_003.png",
        "title": "增值税电子普通发票",
        "invoice_code": "033002200113",
        "invoice_number": "44190582",
        "invoice_date": "2026年11月02日",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "seller_name": "滴滴出行科技有限公司",
        "seller_tax_id": "91110108MA0KX3E4F",
        "items": [("客运服务", "72.02", "9%", "6.48")],
        "excl": "72.02",
        "tax": "6.48",
        "incl": "78.50",
        "incl_cn": "柒拾捌圆伍角整",
        "category": "交通",
        "payee": "孙悦",
        "checker": "周涛",
        "drawer": "吴迪",
    },
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path, index in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=index)
            except OSError:
                continue
    return ImageFont.load_default()


def render(data: dict) -> Image.Image:
    width, height = 860, 1120
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    f_title = load_font(30)
    f_big = load_font(22)
    f_body = load_font(18)
    f_small = load_font(16)

    ink = (32, 40, 56)
    grey = (110, 120, 136)
    line = (188, 196, 208)

    # 外框
    d.rectangle([28, 28, width - 28, height - 28], outline=line, width=2)

    # 标题
    title = data["title"]
    tw = d.textlength(title, font=f_title)
    d.text(((width - tw) / 2, 48), title, font=f_title, fill=ink)

    # 右上角：代码 / 号码 / 日期
    d.text((width - 340, 96), f"发票代码：{data['invoice_code']}", font=f_small, fill=grey)
    d.text((width - 340, 122), f"发票号码：{data['invoice_number']}", font=f_small, fill=ink)
    d.text((width - 340, 148), f"开票日期：{data['invoice_date']}", font=f_small, fill=grey)

    # 购买方
    y = 190
    d.line([48, y - 12, width - 48, y - 12], fill=line)
    d.text((60, y), "购买方", font=f_body, fill=grey)
    d.text((150, y), f"名称：{data['buyer_name']}", font=f_body, fill=ink)
    d.text((150, y + 34), f"纳税人识别号：{data['buyer_tax_id']}", font=f_body, fill=ink)

    # 密码区
    y = 280
    d.rectangle([48, y, width - 48, y + 92], outline=line)
    d.text((60, y + 12), "密 码 区", font=f_small, fill=grey)
    d.text((60, y + 40), "02+9<8*7>45-1/3+2*6>0<", font=load_font(17), fill=(140, 150, 165))
    d.text((60, y + 64), "8<5>1+3/7*2>9<4-6+0/2>", font=load_font(17), fill=(140, 150, 165))

    # 商品表头
    y = 404
    d.line([48, y, width - 48, y], fill=line)
    d.text((60, y + 10), "货物或应税劳务名称", font=f_small, fill=grey)
    d.text((430, y + 10), "金额", font=f_small, fill=grey)
    d.text((540, y + 10), "税率", font=f_small, fill=grey)
    d.text((640, y + 10), "税额", font=f_small, fill=grey)
    d.line([48, y + 44, width - 48, y + 44], fill=line)

    y = 460
    for name, amount, rate, tax in data["items"]:
        d.text((60, y), name, font=f_body, fill=ink)
        d.text((430, y), amount, font=f_body, fill=ink)
        d.text((540, y), rate, font=f_body, fill=ink)
        d.text((640, y), tax, font=f_body, fill=ink)
        y += 40

    # 合计
    d.line([48, y + 10, width - 48, y + 10], fill=line)
    d.text((60, y + 24), "合        计", font=f_body, fill=ink)
    d.text((430, y + 24), f"¥{data['excl']}", font=f_body, fill=ink)
    d.text((640, y + 24), f"¥{data['tax']}", font=f_body, fill=ink)

    # 价税合计
    y += 76
    d.text((60, y), "价税合计（大写）", font=f_body, fill=ink)
    d.text((250, y), data["incl_cn"], font=f_big, fill=ink)
    d.text((620, y + 2), f"（小写）¥{data['incl']}", font=f_big, fill=ink)

    # 销售方
    y += 56
    d.line([48, y - 10, width - 48, y - 10], fill=line)
    d.text((60, y), "销售方", font=f_body, fill=grey)
    d.text((150, y), f"名称：{data['seller_name']}", font=f_body, fill=ink)
    d.text((150, y + 34), f"纳税人识别号：{data['seller_tax_id']}", font=f_body, fill=ink)

    # 底部
    y += 110
    d.line([48, y - 12, width - 48, y - 12], fill=line)
    d.text((60, y), f"收款人：{data['payee']}", font=f_small, fill=grey)
    d.text((300, y), f"复核：{data['checker']}", font=f_small, fill=grey)
    d.text((500, y), f"开票人：{data['drawer']}", font=f_small, fill=grey)

    # 样例水印，避免被当成真票
    f_wm = load_font(56)
    wm = "样 例 数 据"
    ww = d.textlength(wm, font=f_wm)
    wm_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm_layer)
    wd.text(((width - ww) / 2, height / 2 - 40), wm, font=f_wm, fill=(220, 80, 80, 42))
    img = Image.alpha_composite(img.convert("RGBA"), wm_layer).convert("RGB")

    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    truth = []
    for data in SAMPLES:
        img = render(data)
        path = OUT_DIR / data["file"]
        img.save(path, format="PNG", optimize=True)
        truth.append(
            {
                "file": data["file"],
                "invoice_code": data["invoice_code"],
                "invoice_number": data["invoice_number"],
                "invoice_date": f"{data['invoice_date'][:4]}-{data['invoice_date'][5:7]}-{data['invoice_date'][8:10]}",
                "seller_name": data["seller_name"],
                "seller_tax_id": data["seller_tax_id"],
                "buyer_name": data["buyer_name"],
                "buyer_tax_id": data["buyer_tax_id"],
                "amount_excl_tax": float(data["excl"]),
                "tax_amount": float(data["tax"]),
                "amount_incl_tax": float(data["incl"]),
                "category": data["category"],
            }
        )
        print(f"generated {path}")

    (OUT_DIR / "ground_truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"ground truth -> {OUT_DIR / 'ground_truth.json'}")


if __name__ == "__main__":
    main()