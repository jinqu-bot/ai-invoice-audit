"""D1 假数据（fixtures）。

说明三件事：
1. 这些数据是**手写的**，不是模型跑出来的。D2 起会被真实链路替换。
2. 形状已经完全对齐 schemas.py，B 拿到的就是最终形状，不用二次适配。
3. 演示批次 B20261104-001 固定是 5 张：3 绿 + 1 黄 + 1 红。
   另外 3 张放在历史批次里，用来覆盖“转人工 / 敏感类目 / 抬头错”等 UI 状态。
"""

from typing import Any

from app.company import COMPANY_NAME, COMPANY_TAX_ID

DEMO_BATCH_ID = "B20261104-001"
HISTORY_BATCH_ID = "B20261103-002"

IMG = "/api/mock/invoice-image/{}.svg"


def _f(
    code: str,
    number: str,
    date: str,
    seller: str,
    seller_tax: str,
    category: str,
    excl: float,
    tax: float,
    rate: float,
    items: list[tuple[str, float]],
) -> dict[str, Any]:
    return {
        "invoice_code": code,
        "invoice_number": number,
        "invoice_date": date,
        "seller_name": seller,
        "seller_tax_id": seller_tax,
        "buyer_name": COMPANY_NAME,
        "buyer_tax_id": COMPANY_TAX_ID,
        "amount_excl_tax": round(excl, 2),
        "tax_amount": round(tax, 2),
        "amount_incl_tax": round(excl + tax, 2),
        "tax_rate": rate,
        "category": category,
        "items": [{"name": n, "amount": a} for n, a in items],
    }


def _s(
    step: int,
    tool: str,
    title: str,
    reason: str,
    status: str,
    latency_ms: int,
    args: dict | None = None,
    result: dict | None = None,
) -> dict[str, Any]:
    return {
        "step": step,
        "tool": tool,
        "title": title,
        "reason": reason,
        "status": status,
        "latency_ms": latency_ms,
        "args": args,
        "result": result,
    }


# ------------------------------------------------------------------ 制度库

POLICY_DOCS: list[dict] = [
    {
        "doc_id": "P-TRAVEL",
        "title": "差旅费管理办法",
        "version": "v2.1",
        "effective_date": "2026-01-01",
        "article_count": 25,
    },
    {
        "doc_id": "P-ENTERTAIN",
        "title": "业务招待费管理规定",
        "version": "v1.4",
        "effective_date": "2026-03-01",
        "article_count": 15,
    },
    {
        "doc_id": "P-OFFICE",
        "title": "办公用品采购制度",
        "version": "v1.0",
        "effective_date": "2025-07-01",
        "article_count": 15,
    },
]

POLICY_CLAUSES: list[dict] = [
    {
        "doc_id": "P-TRAVEL",
        "doc_title": "差旅费管理办法",
        "article_no": "第 12 条",
        "text": "一线城市住宿费标准为每人每晚 800 元，超出部分需经部门总监审批后方可报销。",
        "score": 0.93,
    },
    {
        "doc_id": "P-TRAVEL",
        "doc_title": "差旅费管理办法",
        "article_no": "第 8 条",
        "text": "报销发票的购买方名称及纳税人识别号必须与公司登记信息完全一致，个人抬头发票不予报销。",
        "score": 0.88,
    },
    {
        "doc_id": "P-TRAVEL",
        "doc_title": "差旅费管理办法",
        "article_no": "第 15 条",
        "text": "差旅费用应在出差结束后 30 日内提交报销，逾期需附情况说明。",
        "score": 0.71,
    },
    {
        "doc_id": "P-ENTERTAIN",
        "doc_title": "业务招待费管理规定",
        "article_no": "第 5 条",
        "text": "业务招待费按人均 120 元标准控制，单次总额不超过 2000 元。",
        "score": 0.90,
    },
    {
        "doc_id": "P-ENTERTAIN",
        "doc_title": "业务招待费管理规定",
        "article_no": "第 9 条",
        "text": "烟酒、礼品、娱乐类支出原则上不予报销，确因业务需要须经分管副总审批。",
        "score": 0.86,
    },
    {
        "doc_id": "P-OFFICE",
        "doc_title": "办公用品采购制度",
        "article_no": "第 4 条",
        "text": "单件办公用品采购金额超过 5000 元的，须走招标比价流程。",
        "score": 0.84,
    },
]


# ------------------------------------------------------------------ 发票明细

DETAILS: list[dict[str, Any]] = [
    # ---------- 演示批次：3 绿 ----------
    {
        "invoice_id": "INV-0001",
        "batch_id": DEMO_BATCH_ID,
        "seq": 1,
        "image_url": IMG.format("INV-0001"),
        "verdict": "pass",
        "headline": "要素齐全，核对通过",
        "confidence": 0.97,
        "manual_review": False,
        "latency_ms": 1180,
        "fields": _f(
            "033002200111", "24815631", "2026-11-01",
            "杭州西溪宾馆有限公司", "91330106MA2K7X1A2B",
            "住宿", 641.51, 38.49, 0.06,
            [("住宿费", 641.51)],
        ),
        "field_confidence": {
            "overall": 0.97,
            "per_field": {
                "invoice_number": 0.99, "invoice_date": 0.98,
                "amount_incl_tax": 0.99, "seller_name": 0.96,
                "buyer_tax_id": 0.97,
            },
        },
        "hit_rules": [],
        "citations": [],
        "suggestions": [],
        "trace": [
            _s(1, "check_duplicate", "查重",
               "查重成本最低、后果最严重，永远第一个做；命中就终止整条审核",
               "miss", 12,
               {"invoice_code": "033002200111", "invoice_number": "24815631"},
               {"hit": False}),
            _s(2, "verify_header", "抬头校验",
               "购买方必须是本公司，否则不能入账",
               "ok", 8, {"buyer_tax_id": COMPANY_TAX_ID}, {"ok": True}),
            _s(3, "query_approval", "审批单核对",
               "确认这笔住宿对应一次真实出差，而不是补票",
               "ok", 23,
               {"employee_id": "E1007", "date_range": "2026-10-31~2026-11-02"},
               {"found": True, "approval_no": "AP-20261031-003"}),
            _s(4, "search_policy", "标准核对",
               "金额 680 元接近一线城市住宿上限，必须核对条款而不是靠硬编码",
               "ok", 156,
               {"category": "住宿", "city_tier": "一线", "amount": 680.0},
               {"limit": 800.0, "clause": "差旅费管理办法 第 12 条"}),
            _s(5, "compose_verdict", "生成结论",
               "所有检查通过，输出结论与可复核依据",
               "ok", 402, None, {"verdict": "pass"}),
        ],
    },
    {
        "invoice_id": "INV-0002",
        "batch_id": DEMO_BATCH_ID,
        "seq": 2,
        "image_url": IMG.format("INV-0002"),
        "verdict": "pass",
        "headline": "人均 119.3 元，未超招待标准",
        "confidence": 0.95,
        "manual_review": False,
        "latency_ms": 1240,
        "fields": _f(
            "033002200112", "31027744", "2026-10-30",
            "杭州鲜味餐饮管理有限公司", "91330106MA2K7X2C3D",
            "招待", 337.74, 20.26, 0.06,
            [("餐饮服务", 337.74)],
        ),
        "field_confidence": {
            "overall": 0.95,
            "per_field": {"invoice_number": 0.97, "invoice_date": 0.96, "amount_incl_tax": 0.98},
        },
        "hit_rules": [],
        "citations": [
            {
                "doc_id": "P-ENTERTAIN",
                "doc_title": "业务招待费管理规定",
                "article_no": "第 5 条",
                "text": "业务招待费按人均 120 元标准控制，单次总额不超过 2000 元。",
                "score": 0.91,
            }
        ],
        "suggestions": [],
        "trace": [
            _s(1, "check_duplicate", "查重", "查重优先，命中即终止", "miss", 11),
            _s(2, "verify_header", "抬头校验", "购买方主体一致性", "ok", 7),
            _s(3, "search_policy", "标准核对",
               "招待费看人均而不是总额，必须知道用餐人数才能判",
               "ok", 168,
               {"category": "招待", "amount": 358.0, "headcount": 3},
               {"per_person": 119.33, "limit": 120.0}),
            _s(4, "compose_verdict", "生成结论", "输出结论与引用条款", "ok", 388),
        ],
    },
    {
        "invoice_id": "INV-0003",
        "batch_id": DEMO_BATCH_ID,
        "seq": 3,
        "image_url": IMG.format("INV-0003"),
        "verdict": "pass",
        "headline": "市内交通，金额正常",
        "confidence": 0.96,
        "manual_review": False,
        "latency_ms": 980,
        "fields": _f(
            "033002200113", "44190582", "2026-11-02",
            "滴滴出行科技有限公司", "91110108MA0KX3E4F",
            "交通", 72.02, 6.48, 0.09,
            [("客运服务", 72.02)],
        ),
        "field_confidence": {
            "overall": 0.96,
            "per_field": {"invoice_number": 0.98, "amount_incl_tax": 0.99},
        },
        "hit_rules": [],
        "citations": [],
        "suggestions": [],
        "trace": [
            _s(1, "check_duplicate", "查重", "查重优先，命中即终止", "miss", 10),
            _s(2, "verify_header", "抬头校验", "购买方主体一致性", "ok", 6),
            _s(3, "search_policy", "标准核对",
               "金额远低于阈值，跳过条款检索以节省一次调用",
               "skip", 0, {"reason": "金额 < 阈值 30%"}, {"skipped": True}),
            _s(4, "compose_verdict", "生成结论", "输出结论", "ok", 351),
        ],
    },

    # ---------- 演示批次：1 黄 ----------
    {
        "invoice_id": "INV-0004",
        "batch_id": DEMO_BATCH_ID,
        "seq": 4,
        "image_url": IMG.format("INV-0004"),
        "verdict": "suspect",
        "headline": "超出住宿标准 480 元，需总监审批",
        "confidence": 0.94,
        "manual_review": False,
        "latency_ms": 1620,
        "fields": _f(
            "033002200114", "58231067", "2026-10-31",
            "杭州西溪宾馆有限公司", "91330106MA2K7X1A2B",
            "住宿", 1207.55, 72.45, 0.06,
            [("住宿费", 1207.55)],
        ),
        "field_confidence": {
            "overall": 0.94,
            "per_field": {"invoice_number": 0.97, "amount_incl_tax": 0.93},
        },
        "hit_rules": [
            {
                "code": "R5",
                "name": "超出费用标准",
                "level": "suspect",
                "detail": "住宿 1280 元/晚，超出一线城市标准 800 元/晚，差额 480 元",
                "evidence": {"limit": 800.0, "actual": 1280.0, "diff": 480.0, "city_tier": "一线"},
            }
        ],
        "citations": [
            {
                "doc_id": "P-TRAVEL",
                "doc_title": "差旅费管理办法",
                "article_no": "第 12 条",
                "text": "一线城市住宿费标准为每人每晚 800 元，超出部分需经部门总监审批后方可报销。",
                "score": 0.93,
            }
        ],
        "suggestions": [
            "补充部门总监的书面审批意见后重新提交",
            "或将报销金额调整为 800 元，差额部分自行承担",
        ],
        "trace": [
            _s(1, "check_duplicate", "查重", "查重优先，命中即终止", "miss", 11),
            _s(2, "verify_header", "抬头校验", "购买方主体一致性", "ok", 7),
            _s(3, "query_approval", "审批单核对", "确认出差真实性", "ok", 19),
            _s(4, "search_policy", "标准核对",
               "金额 1280 明显高于阈值，检索条款以取得可引用的依据",
               "hit", 173,
               {"category": "住宿", "city_tier": "一线", "amount": 1280.0},
               {"limit": 800.0, "diff": 480.0, "clause": "差旅费管理办法 第 12 条"}),
            _s(5, "compose_verdict", "生成结论", "命中超标准，输出存疑并附条款", "hit", 452),
        ],
    },

    # ---------- 演示批次：1 红 ----------
    {
        "invoice_id": "INV-0005",
        "batch_id": DEMO_BATCH_ID,
        "seq": 5,
        "image_url": IMG.format("INV-0005"),
        "verdict": "reject",
        "headline": "该发票已于 11-02 由张伟报销",
        "confidence": 0.98,
        "manual_review": False,
        "latency_ms": 210,
        "fields": _f(
            "033002200115", "66472890", "2026-10-28",
            "杭州老码头餐饮管理有限公司", "91330102MA2K7X5G6H",
            "餐饮", 458.49, 27.51, 0.06,
            [("餐饮服务", 458.49)],
        ),
        "field_confidence": {
            "overall": 0.98,
            "per_field": {"invoice_number": 0.99, "amount_incl_tax": 0.99},
        },
        "hit_rules": [
            {
                "code": "R1",
                "name": "重复报销",
                "level": "reject",
                "detail": "该发票已于 2026-11-02 由张伟（销售部）在报销单 BX-1102-007 中提交",
                "evidence": {
                    "reimbursement_no": "BX-1102-007",
                    "employee": "张伟",
                    "dept": "销售部",
                    "submitted_at": "2026-11-02 15:21",
                },
            }
        ],
        "citations": [],
        "suggestions": [
            "请勿重复提交；如确属另一笔业务，请联系财务核实发票号码是否录入错误",
        ],
        "trace": [
            _s(1, "check_duplicate", "查重",
               "查重成本最低、后果最严重，永远第一个做；命中即终止整条审核",
               "hit", 12,
               {"invoice_code": "033002200115", "invoice_number": "66472890"},
               {"hit": True, "reimbursement_no": "BX-1102-007"}),
            _s(2, "short_circuit", "终止后续审核",
               "已命中重复报销，继续查标准没有意义，直接出结论——这一步就是“会停”",
               "skip", 1, {"skipped": ["verify_header", "query_approval", "search_policy"]}),
            _s(3, "compose_verdict", "生成结论", "输出驳回结论与历史单号", "hit", 198),
        ],
    },

    # ---------- 历史批次：覆盖其余 UI 状态 ----------
    {
        "invoice_id": "INV-0006",
        "batch_id": HISTORY_BATCH_ID,
        "seq": 1,
        "image_url": IMG.format("INV-0006"),
        "verdict": "reject",
        "headline": "发票抬头不是本公司，无法入账",
        "confidence": 0.93,
        "manual_review": False,
        "latency_ms": 340,
        "fields": _f(
            "033002200116", "77015543", "2026-10-26",
            "浙江大华办公用品有限公司", "91330100MA2K7X6H7J",
            "办公", 2831.86, 368.14, 0.13,
            [("办公耗材", 2831.86)],
        ),
        "field_confidence": {
            "overall": 0.93,
            "per_field": {"buyer_name": 0.88, "buyer_tax_id": 0.86},
        },
        "hit_rules": [
            {
                "code": "R3",
                "name": "抬头或税号不符",
                "level": "reject",
                "detail": "发票购买方为“杭州云帆网络科技有限公司”，与本公司“杭州云帆科技有限公司”不一致",
                "evidence": {"expected": COMPANY_NAME, "actual": "杭州云帆网络科技有限公司"},
            }
        ],
        "citations": [
            {
                "doc_id": "P-TRAVEL",
                "doc_title": "差旅费管理办法",
                "article_no": "第 8 条",
                "text": "报销发票的购买方名称及纳税人识别号必须与公司登记信息完全一致，个人抬头发票不予报销。",
                "score": 0.88,
            }
        ],
        "suggestions": ["联系供应商作废重开，抬头须为“杭州云帆科技有限公司”", "重开后再提交报销"],
        "trace": [
            _s(1, "check_duplicate", "查重", "查重优先，命中即终止", "miss", 11),
            _s(2, "verify_header", "抬头校验",
               "购买方必须是本公司，名称或税号任一不符即驳回",
               "hit", 9,
               {"buyer_name": "杭州云帆网络科技有限公司"},
               {"ok": False, "diff": "购买方名称不一致"}),
            _s(3, "compose_verdict", "生成结论", "输出驳回结论与重开指引", "hit", 312),
        ],
    },
    {
        "invoice_id": "INV-0007",
        "batch_id": HISTORY_BATCH_ID,
        "seq": 2,
        "image_url": IMG.format("INV-0007"),
        "verdict": "suspect",
        "headline": "含酒水消费，需专项审批",
        "confidence": 0.92,
        "manual_review": False,
        "latency_ms": 1450,
        "fields": _f(
            "033002200117", "88130022", "2026-10-24",
            "杭州酒家餐饮有限公司", "91330102MA2K7X7K8L",
            "招待", 1584.91, 95.09, 0.06,
            [("餐饮服务", 1383.02), ("酒水", 201.89)],
        ),
        "field_confidence": {
            "overall": 0.92,
            "per_field": {"invoice_number": 0.96, "amount_incl_tax": 0.94},
        },
        "hit_rules": [
            {
                "code": "R8",
                "name": "敏感类目",
                "level": "suspect",
                "detail": "消费明细含“酒水”201.89 元，属于需专项审批类目",
                "evidence": {"matched": "酒水", "amount": 201.89},
            }
        ],
        "citations": [
            {
                "doc_id": "P-ENTERTAIN",
                "doc_title": "业务招待费管理规定",
                "article_no": "第 9 条",
                "text": "烟酒、礼品、娱乐类支出原则上不予报销，确因业务需要须经分管副总审批。",
                "score": 0.86,
            }
        ],
        "suggestions": ["补充招待事由与客户名单", "取得分管副总的书面审批"],
        "trace": [
            _s(1, "check_duplicate", "查重", "查重优先，命中即终止", "miss", 11),
            _s(2, "verify_header", "抬头校验", "购买方主体一致性", "ok", 7),
            _s(3, "scan_items", "明细扫描",
               "总额合规不代表明细合规，必须逐项看类目",
               "hit", 38, {"items": ["餐饮服务", "酒水"]}, {"matched": "酒水", "amount": 201.89}),
            _s(4, "search_policy", "依据检索", "取得敏感类目的制度依据", "ok", 164),
            _s(5, "compose_verdict", "生成结论", "输出存疑并附条款", "hit", 431),
        ],
    },
    {
        "invoice_id": "INV-0008",
        "batch_id": HISTORY_BATCH_ID,
        "seq": 3,
        "image_url": IMG.format("INV-0008"),
        "verdict": "manual",
        "headline": "识别置信度 0.61，已转人工复核",
        "confidence": 0.61,
        "manual_review": True,
        "latency_ms": 2260,
        "fields": _f(
            "033002200118", "99204615", "2026-10-22",
            "杭州西溪宾馆有限公司", "91330106MA2K7X1A2B",
            "住宿", 528.30, 31.70, 0.06,
            [("住宿费", 528.30)],
        ),
        "field_confidence": {
            "overall": 0.61,
            "per_field": {"invoice_number": 0.42, "invoice_date": 0.55, "amount_incl_tax": 0.68},
        },
        "hit_rules": [
            {
                "code": "R0",
                "name": "识别置信度不足",
                "level": "manual",
                "detail": "发票照片倾斜且金额区域被印章遮挡，关键字段置信度低于 0.80",
                "evidence": {"threshold": 0.8, "invoice_number_conf": 0.42},
            }
        ],
        "citations": [],
        "suggestions": ["请重新拍摄清晰照片（平铺、无遮挡、光线均匀）", "或手动补录发票号码与金额后重新审核"],
        "trace": [
            _s(1, "extract_fields", "要素抽取",
               "先抽取，再判断有没有资格继续往下审",
               "ok", 2180, {"image": "INV-0008"}, {"overall_conf": 0.61}),
            _s(2, "confidence_gate", "置信度闸门",
               "把握不够就不审——宁可交给人，也不给一个可能是错的结论",
               "skip", 2, {"threshold": 0.8}, {"action": "manual_review"}),
        ],
    },
]


# ------------------------------------------------------------------ 批次汇总

BATCHES: dict[str, dict[str, Any]] = {
    DEMO_BATCH_ID: {
        "batch_id": DEMO_BATCH_ID,
        "created_at": "2026-11-04 09:12:38",
        "invoice_count": 5,
        "status": "done",
        "elapsed_ms": 5230,
    },
    HISTORY_BATCH_ID: {
        "batch_id": HISTORY_BATCH_ID,
        "created_at": "2026-11-03 16:40:12",
        "invoice_count": 3,
        "status": "done",
        "elapsed_ms": 3960,
    },
}


def card_of(detail: dict[str, Any]) -> dict[str, Any]:
    """把明细压成结果页卡片需要的字段。"""
    f = detail["fields"]
    return {
        "invoice_id": detail["invoice_id"],
        "provider": "fixture",
        "batch_id": detail["batch_id"],
        "seq": detail["seq"],
        "image_url": detail["image_url"],
        "verdict": detail["verdict"],
        "headline": detail["headline"],
        "seller_name": f["seller_name"],
        "invoice_number": f["invoice_number"],
        "invoice_date": f["invoice_date"],
        "amount_incl_tax": f["amount_incl_tax"],
        "category": f["category"],
        "confidence": detail["confidence"],
        "manual_review": detail["manual_review"],
        "hit_rule_codes": [r["code"] for r in detail["hit_rules"]],
        "latency_ms": detail["latency_ms"],
    }


def items_of(batch_id: str) -> list[dict[str, Any]]:
    return [card_of(d) for d in DETAILS if d["batch_id"] == batch_id]


def summary_of(batch_id: str) -> dict[str, Any]:
    base = dict(BATCHES[batch_id])
    items = [d for d in DETAILS if d["batch_id"] == batch_id]
    counts = {"pass": 0, "suspect": 0, "reject": 0, "manual": 0}
    for d in items:
        counts[d["verdict"]] += 1
    base.update(
        {
            "total_amount": round(sum(d["fields"]["amount_incl_tax"] for d in items), 2),
            "pass_count": counts["pass"],
            "suspect_count": counts["suspect"],
            "reject_count": counts["reject"],
            "manual_count": counts["manual"],
        }
    )
    return base


def get_detail(invoice_id: str) -> dict[str, Any] | None:
    for d in DETAILS:
        if d["invoice_id"] == invoice_id:
            return d
    return None


# ------------------------------------------------------------------ 看板（聚合假数据）

DASHBOARD: dict[str, Any] = {
    "month": "2026-11",
    "total_count": 128,
    "total_amount": 186420.50,
    "pass_rate": 0.72,
    "reject_reasons": [
        {"name": "重复报销", "count": 9},
        {"name": "抬头或税号不符", "count": 7},
        {"name": "超出费用标准", "count": 6},
        {"name": "敏感类目", "count": 4},
        {"name": "缺少审批单", "count": 3},
    ],
    "by_department": [
        {"dept": "销售部", "amount": 78210.00, "count": 52},
        {"dept": "市场部", "amount": 45120.50, "count": 31},
        {"dept": "技术部", "amount": 32880.00, "count": 27},
        {"dept": "行政部", "amount": 30210.00, "count": 18},
    ],
    "by_category": [
        {"name": "住宿", "count": 48},
        {"name": "餐饮", "count": 36},
        {"name": "交通", "count": 28},
        {"name": "办公", "count": 11},
        {"name": "招待", "count": 5},
    ],
    "by_supplier": [
        {"dept": "杭州西溪宾馆有限公司", "amount": 42600.00, "count": 33},
        {"dept": "杭州鲜味餐饮管理有限公司", "amount": 28140.00, "count": 24},
        {"dept": "滴滴出行科技有限公司", "amount": 12860.50, "count": 21},
        {"dept": "浙江大华办公用品有限公司", "amount": 9420.00, "count": 8},
    ],
    "amount_buckets": [
        {"name": "0-100", "count": 34},
        {"name": "100-500", "count": 41},
        {"name": "500-1000", "count": 28},
        {"name": "1000-2000", "count": 19},
        {"name": "2000+", "count": 6},
    ],
    "daily_trend": [
        {"name": "11-01", "count": 18},
        {"name": "11-02", "count": 24},
        {"name": "11-03", "count": 21},
        {"name": "11-04", "count": 31},
    ],
}
