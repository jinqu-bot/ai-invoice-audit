"""抽取结果的四道关。

顺序是有讲究的：
  1. 格式关 —— 字段在不在、类型对不对
  2. 算术关 —— 不含税 + 税额 ≈ 价税合计（模型最爱在这里翻车）
  3. 常识关 —— 日期不能是明年、税号不能 12 位
  4. 把握关 —— 交给 extract.py，这里不管

前两关的错误会回灌给模型重试；第三关只提示，不重试（重试也改不了）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

CATEGORIES = {"住宿", "餐饮", "交通", "办公", "招待", "其他"}
LEGAL_TAX_RATES = {0.0, 0.01, 0.03, 0.05, 0.06, 0.09, 0.13}
REQUIRED_FIELDS = [
    "invoice_number",
    "invoice_date",
    "seller_name",
    "buyer_name",
    "amount_incl_tax",
]
ARITHMETIC_TOLERANCE = 0.02  # 一分钱以内的四舍五入误差放过


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("¥", "").replace("￥", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def to_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def check_schema(data: dict) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if data.get(field) in (None, "", []):
            errors.append(f"字段 {field} 缺失或为空")
    if data.get("amount_incl_tax") is not None and to_float(data["amount_incl_tax"]) is None:
        errors.append("amount_incl_tax 不是合法数字")
    if data.get("invoice_date") is not None and to_date(data["invoice_date"]) is None:
        errors.append("invoice_date 不是合法日期（要求 YYYY-MM-DD）")
    if not isinstance(data.get("items", []), list):
        errors.append("items 必须是数组")
    return errors


def check_arithmetic(data: dict) -> list[str]:
    excl = to_float(data.get("amount_excl_tax"))
    tax = to_float(data.get("tax_amount"))
    incl = to_float(data.get("amount_incl_tax"))

    if excl is None or tax is None or incl is None:
        return []  # 缺项交给格式关

    diff = round(excl + tax - incl, 2)
    if abs(diff) > ARITHMETIC_TOLERANCE:
        return [
            f"金额勾稽不通过：不含税 {excl:.2f} + 税额 {tax:.2f} = {excl + tax:.2f}，"
            f"与价税合计 {incl:.2f} 相差 {diff:+.2f}"
        ]
    return []


def check_sanity(data: dict) -> list[str]:
    """返回的是 warnings——这些问题重试也修不好，只能提示。"""
    warnings: list[str] = []
    today = date.today()

    inv_date = to_date(data.get("invoice_date"))
    if inv_date:
        if inv_date > today:
            warnings.append(f"开票日期 {inv_date} 晚于今天，疑似识别错误")
        elif (today - inv_date).days > 365 * 5:
            warnings.append(f"开票日期 {inv_date} 距今超过 5 年")

    number = str(data.get("invoice_number") or "").strip()
    if number and not number.isdigit():
        warnings.append(f"发票号码 {number} 含非数字字符")
    elif number and len(number) not in (8, 20):
        warnings.append(f"发票号码长度 {len(number)} 位，常见为 8 位或 20 位")

    for key, label in (("buyer_tax_id", "购买方税号"), ("seller_tax_id", "销售方税号")):
        tax_id = str(data.get(key) or "").strip()
        if tax_id and len(tax_id) not in (15, 17, 18, 20):
            warnings.append(f"{label}长度异常（{len(tax_id)} 位）")

    rate = to_float(data.get("tax_rate"))
    if rate is not None:
        normalized = rate / 100 if rate > 1 else rate
        if round(normalized, 4) not in LEGAL_TAX_RATES:
            warnings.append(f"税率 {rate} 不在常见档位（0/1%/3%/5%/6%/9%/13%）")

    category = data.get("category")
    if category and category not in CATEGORIES:
        warnings.append(f"费用类目「{category}」不在允许集合内")

    incl = to_float(data.get("amount_incl_tax"))
    if incl is not None and incl <= 0:
        warnings.append("价税合计为 0 或负数")

    return warnings


def validate(data: dict) -> dict:
    """跑完前两关，返回报告字典（结构与 ValidationReport 一致）。"""
    schema_errors = check_schema(data)
    arithmetic_errors = check_arithmetic(data)
    warnings = check_sanity(data)

    return {
        "schema_ok": not schema_errors,
        "arithmetic_ok": not arithmetic_errors,
        "sanity_ok": not warnings,
        "errors": schema_errors + arithmetic_errors,
        "warnings": warnings,
    }
