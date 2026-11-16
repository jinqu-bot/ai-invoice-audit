"""公司配置：抬头 / 税号 / 期限 / 标准。

这一组测的是"换一家公司能不能不改代码"：
配置写进库、接口读得到、规则真的按新配置判。
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ExtractedFields, InvoiceItem
from app.services import history, profile
from app.services.rules import run_audit

client = TestClient(app)

NEW_COMPANY = {
    "name": "宁波海川贸易有限公司",
    "tax_id": "91330200MA2H8K7L6M",
    "deadline_days": 45,
    "limits": {"住宿": 1200.0, "招待": 3000.0, "办公": 8000.0},
}


def make_fields(**overrides) -> ExtractedFields:
    base = {
        "invoice_code": "033002200198",
        "invoice_number": "88880001",
        "invoice_date": date.today().isoformat(),
        "seller_name": "杭州西溪宾馆有限公司",
        "seller_tax_id": "91330106MA2K7X1A2B",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "amount_excl_tax": 641.51,
        "tax_amount": 38.49,
        "amount_incl_tax": 680.00,
        "tax_rate": 0.06,
        "category": "住宿",
        "items": [InvoiceItem(name="住宿费", amount=641.51)],
    }
    base.update(overrides)
    return ExtractedFields(**base)


def audit(fields: ExtractedFields, confidence: float = 0.95):
    return run_audit(
        fields,
        confidence=confidence,
        is_invoice=True,
        history=history,
    )


# ------------------------------------------------------------------ 默认值

def test_default_company_is_builtin():
    r = client.get("/api/settings/company")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "杭州云帆科技有限公司"
    assert body["tax_id"] == "91330100MA2A1B2C3D"
    assert body["deadline_days"] == 30
    assert body["limits"]["住宿"] == 800.0
    assert body["is_default"] is True


# ------------------------------------------------------------------ 保存

def test_save_company_takes_effect_immediately():
    r = client.put("/api/settings/company", json=NEW_COMPANY)
    assert r.status_code == 200
    saved = r.json()
    assert saved["name"] == NEW_COMPANY["name"]
    assert saved["is_default"] is False
    assert saved["updated_at"]

    again = client.get("/api/settings/company").json()
    assert again["tax_id"] == NEW_COMPANY["tax_id"]
    assert again["deadline_days"] == 45


def test_tax_id_is_upper_cased_and_trimmed():
    payload = dict(NEW_COMPANY, name="  宁波海川贸易有限公司  ", tax_id=" 91330200ma2h8k7l6m ")
    saved = client.put("/api/settings/company", json=payload).json()
    assert saved["name"] == "宁波海川贸易有限公司"
    assert saved["tax_id"] == "91330200MA2H8K7L6M"


def test_invalid_tax_id_is_rejected():
    payload = dict(NEW_COMPANY, tax_id="123")
    r = client.put("/api/settings/company", json=payload)
    assert r.status_code == 422
    assert "纳税人识别号" in r.json()["message"]


def test_unknown_category_is_rejected():
    payload = dict(NEW_COMPANY, limits={"餐饮": 100.0})
    r = client.put("/api/settings/company", json=payload)
    assert r.status_code == 422
    assert "费用类目" in r.json()["message"]


# ------------------------------------------------------------------ 规则跟着配置走

def test_header_check_uses_configured_company():
    """把公司换成宁波海川之后：新公司抬头通过，老抬头反而被驳回。"""
    client.put("/api/settings/company", json=NEW_COMPANY)

    matched = audit(make_fields(buyer_name=NEW_COMPANY["name"], buyer_tax_id=NEW_COMPANY["tax_id"]))
    assert "R3" not in [hit["code"] for hit in matched.hits]
    assert matched.verdict == "pass"

    old = audit(make_fields(buyer_name="杭州云帆科技有限公司", buyer_tax_id="91330100MA2A1B2C3D"))
    assert "R3" in [hit["code"] for hit in old.hits]
    assert old.verdict == "reject"


def test_deadline_and_limits_follow_config():
    """期限 45 天、住宿 1200：40 天前的票不算超期，1100 元的住宿不算超标。"""
    client.put("/api/settings/company", json=NEW_COMPANY)
    from datetime import timedelta

    fields = make_fields(
        buyer_name=NEW_COMPANY["name"],
        buyer_tax_id=NEW_COMPANY["tax_id"],
        invoice_date=(date.today() - timedelta(days=40)).isoformat(),
        amount_excl_tax=1037.74,
        tax_amount=62.26,
        amount_incl_tax=1100.0,
        items=[InvoiceItem(name="住宿费", amount=1037.74)],
    )
    result = audit(fields)
    codes = [hit["code"] for hit in result.hits]
    assert "R4" not in codes, "40 天在 45 天窗口内，不该报超期"
    assert "R5" not in codes, "1100 元低于配置的 1200 标准"
    assert result.verdict == "pass"


def test_profile_falls_back_to_defaults_when_table_missing(monkeypatch):
    """库读不出来时退回默认，不能让一次数据库抖动把审核堵死。"""
    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(profile.db, "one", boom)
    assert profile.get()["name"] == "杭州云帆科技有限公司"