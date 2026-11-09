"""规则引擎（D4）：把"识别出来的字段"变成"这张票该不该报"。

三条设计原则，答辩时可以直接讲：

1. **每条规则都要指得出制度第几条**，指不出就不下结论、只提提示。
2. **查重最先跑，命中即终止**——已经重复报销了，继续核标准是浪费，
   "会停"本身就是 Agent 该有的判断。
3. **拿不准就交给人（manual），不硬下结论**。宁可少判一张，不可错杀一张。

结论优先级：reject > manual > suspect > pass。
理由：驳回是基于事实（重号、抬头错），manual 是"我不知道"，
suspect 是"我知道有问题但可补救"。事实压过不确定，不确定压过可补救。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.company import COMPANY_NAME, COMPANY_TAX_ID
from app.config import settings
from app.schemas import ExtractedFields
from app.services import policy
from app.services.validators import LEGAL_TAX_RATES

# 差旅费管理办法 第 15 条：出差结束后 30 日内提交
DEADLINE_DAYS = 30

# 费用标准。住宿只对一线给了 800，其他城市原文没写，
# 这里统一按 800 卡上限——宽松处理，宁可漏判也不误伤。
LIMITS: dict[str, dict[str, Any]] = {
    "住宿": {"limit": 800.0, "doc": ("P-TRAVEL", "第 12 条"), "unit": "晚"},
    "招待": {"limit": 2000.0, "doc": ("P-ENTERTAIN", "第 5 条"), "unit": "次"},
    "办公": {"limit": 5000.0, "doc": ("P-OFFICE", "第 4 条"), "unit": "笔"},
}

# 类目与法定税率。住宿/餐饮/招待开的是生活服务，6%（小规模 3% / 1%）；
# 交通是 9%；办公既可能是服务费 6%，也可能是办公用品货物 13%，两种都算合法。
# 「其他」不做限定——硬套一张表最后只会变成误伤。
CATEGORY_TAX_RATES: dict[str, set[float]] = {
    "住宿": {0.06, 0.03, 0.01},
    "餐饮": {0.06, 0.03, 0.01},
    "招待": {0.06, 0.03, 0.01},
    "交通": {0.09, 0.03, 0.01},
    "办公": {0.06, 0.13, 0.03, 0.01},
}

# 第 9 条点名的那几类，以及实际会出现的近义词。
# 单字「烟」「酒」放在最后：命中的是第一个词，具体的写法要优先报出来，
# 否则"白酒"会被报成"酒"，结论看着像模型说错了话。
# 单字会带来误伤（"烟花"、"酒店"）——但这条只出黄灯转人工，不直接驳回，
# 代价是可接受的；漏掉真烟酒才是真损失。
SENSITIVE_WORDS = [
    "酒水", "白酒", "红酒", "啤酒", "香烟", "烟草", "礼品", "娱乐",
    "KTV", "按摩", "游戏点卡", "购物卡", "储值卡", "烟", "酒",
]

REQUIRED_FIELDS: list[tuple[str, str]] = [
    ("invoice_number", "发票号码"),
    ("invoice_date", "开票日期"),
    ("seller_name", "销售方名称"),
    ("buyer_name", "购买方名称"),
    ("amount_incl_tax", "价税合计"),
]

# 规则清单。前端"我们用哪些规则"那一页、以及 /api/rules 都读这里，
# 不要在别处再写一份——写两份就会有一份过期。
RULES: list[dict[str, Any]] = [
    {
        "code": "R0",
        "name": "识别置信度不足",
        "level": "manual",
        "why": "要素都没抄准，后面的判断再漂亮也是错的。所以这一关卡在最前面。",
        "trigger": "关键字段置信度低于阈值，或校验不通过，或这张图根本不是发票",
        "basis": None,
    },
    {
        "code": "R1",
        "name": "重复报销",
        "level": "reject",
        "why": "同一张发票报两次，是报销里最常见也最贵的错，且一查一个准。",
        "trigger": "发票号码在报销台账里已经存在",
        "basis": None,
    },
    {
        "code": "R2",
        "name": "关键要素缺失",
        "level": "manual",
        "why": "缺号码、缺日期就没法查重也没法入账，机器不应该替人补。",
        "trigger": "发票号码/日期/销售方/购买方/价税合计任一为空",
        "basis": None,
    },
    {
        "code": "R3",
        "name": "抬头或税号不符",
        "level": "reject",
        "why": "抬头不是本公司，这张票在税务上根本不能入账，金额再小也白搭。",
        "trigger": "购买方名称或纳税人识别号与公司登记信息不一致",
        "basis": ("P-TRAVEL", "第 8 条"),
    },
    {
        "code": "R4",
        "name": "超期提交",
        "level": "suspect",
        "why": "制度给了 30 天窗口，超期不是不能报，但要有说法。",
        "trigger": f"开票日期距今超过 {DEADLINE_DAYS} 天",
        "basis": ("P-TRAVEL", "第 15 条"),
    },
    {
        "code": "R5",
        "name": "超出费用标准",
        "level": "suspect",
        "why": "标准写在制度里，不是财务的心情。超了就要有审批，而不是靠人记。",
        "trigger": "住宿超 800/晚、招待单次超 2000、办公单笔超 5000",
        "basis": ("P-TRAVEL", "第 12 条"),
    },
    {
        "code": "R6",
        "name": "明细与合计不符",
        "level": "suspect",
        "why": "总额对得上不代表明细对得上，拆票、塞项目都藏在这一层。",
        "trigger": "明细行金额之和与不含税金额相差超过 0.02 元",
        "basis": None,
    },
    {
        "code": "R7",
        "name": "税率或税额异常",
        "level": "suspect",
        "why": "税额 = 不含税 × 税率，这一步对不上，说明票面本身可疑。",
        "trigger": "税率不在法定档位、与费用类目明显不符，或税额与「不含税 × 税率」相差超过 0.05 元",
        "basis": None,
    },
    {
        "code": "R8",
        "name": "敏感类目",
        "level": "suspect",
        "why": "总额合规不代表明细合规，烟酒娱乐是明确点名要专项审批的。",
        "trigger": "消费明细里出现酒水、烟、礼品、娱乐类字样",
        "basis": ("P-ENTERTAIN", "第 9 条"),
    },
]

_RULE_INDEX: dict[str, dict[str, Any]] = {rule["code"]: rule for rule in RULES}

LEVEL_ORDER = {"reject": 3, "manual": 2, "suspect": 1}


def rule_defs() -> list[dict[str, Any]]:
    """给 /api/rules 用的完整定义，附上条款原文。"""
    out: list[dict[str, Any]] = []
    for rule in RULES:
        basis_doc = basis_article = basis_text = None
        if rule["basis"]:
            doc_id, article_no = rule["basis"]
            found = policy.clause(doc_id, article_no)
            if found:
                basis_doc = found["doc_title"]
                basis_article = found["article_no"]
                basis_text = found["text"]
        out.append(
            {
                "code": rule["code"],
                "name": rule["name"],
                "level": rule["level"],
                "why": rule["why"],
                "trigger": rule["trigger"],
                "basis_doc": basis_doc,
                "basis_article": basis_article,
                "basis_text": basis_text,
            }
        )
    return out


@dataclass
class AuditResult:
    verdict: str
    hits: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    headline: str = ""
    suggestions: list[str] = field(default_factory=list)


class _Ctx:
    """收集命中、引用、轨迹。省得每个检查都返回一大串元组。"""

    def __init__(self, start_step: int, today: date) -> None:
        self.today = today
        self.hits: list[dict[str, Any]] = []
        self.citations: list[dict[str, Any]] = []
        self.steps: list[dict[str, Any]] = []
        self.tips: list[str] = []
        self._step_no = start_step
        self._cite_keys: set[tuple[str, str]] = set()

    def step(
        self,
        tool: str,
        title: str,
        reason: str,
        status: str,
        args: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        latency_ms: int = 0,
    ) -> None:
        self.steps.append(
            {
                "step": self._step_no,
                "tool": tool,
                "title": title,
                "reason": reason,
                "status": status,
                "latency_ms": latency_ms,
                "args": args,
                "result": result,
            }
        )
        self._step_no += 1

    def cite(self, doc_id: str, article_no: str, score: float | None = None) -> None:
        if (doc_id, article_no) in self._cite_keys:
            return
        found = policy.cite(doc_id, article_no, score)
        if found:
            self._cite_keys.add((doc_id, article_no))
            self.citations.append(found)

    def hit(
        self,
        code: str,
        detail: str,
        evidence: dict[str, Any] | None = None,
        citation: tuple[str, str] | None = None,
        tip: str | None = None,
    ) -> None:
        rule = _RULE_INDEX[code]
        self.hits.append(
            {
                "code": code,
                "name": rule["name"],
                "level": rule["level"],
                "detail": detail,
                "evidence": evidence or {},
            }
        )
        if citation:
            self.cite(*citation)
        if tip:
            self.tips.append(tip)


# ------------------------------------------------------------------ 单条规则

def _check_duplicate(ctx: _Ctx, fields: ExtractedFields, history: Any) -> bool:
    """R1。命中返回 True，调用方据此短路。"""
    number = (fields.invoice_number or "").strip()
    found = history.find(number, fields.invoice_code) if number else None
    if found:
        # 台账的实现可能不同（数据库 / 测试替身 / 以后的远端系统），
        # 结论依赖的是"报过没有"，不是"字段齐不齐"——所以取值一律容错。
        submitted = str(found.get("submitted_at") or "")[:10] or "更早"
        employee = found.get("employee") or "未登记"
        if employee in ("报销人", "他人"):
            employee = "未登记"
        source = found.get("source", "unknown")
        prefix = "演示样例号码重复" if source in ("mock-vlm", "fixture") else "与既往审核记录号码重复"
        dept = found.get("dept") or "—"
        reimbursement_no = found.get("reimbursement_no") or "—"
        detail = (
            f"{prefix}：{submitted} 的记录 {reimbursement_no}（报销人：{employee}）。"
            "审核记录不代表已完成真实报销，请核对原票与财务台账。"
        )
        ctx.hit(
            "R1",
            detail,
            evidence={
                "reimbursement_no": reimbursement_no,
                "employee": employee,
                "source": source,
                "dept": dept,
                "submitted_at": found.get("submitted_at"),
            },
            tip=("演示号码命中样例记录，不代表原票重复；请接入模型后重新审核原图"
                 if source in ("mock-vlm", "fixture") else
                 "请核对原票号码及既往审核记录，确认是否重复提交；该记录不代表已完成报销"),
        )
        ctx.step(
            "check_duplicate",
            "查重",
            "查重成本最低、后果最严重，永远第一个做；命中即终止整条审核",
            "hit",
            {"invoice_number": number},
            {"hit": True, "reimbursement_no": reimbursement_no},
        )
        ctx.step(
            "short_circuit",
            "终止后续审核",
            "号码与同来源记录重复，暂停后续审核，交由人工核实原票及提交记录",
            "skip",
            {"skipped": ["verify_header", "check_completeness", "check_deadline", "check_standard"]},
        )
        return True

    ctx.step(
        "check_duplicate",
        "查重",
        "查重成本最低、后果最严重，永远第一个做；命中即终止整条审核",
        "miss",
        {"invoice_number": number},
        {"hit": False},
    )
    return False


def _check_completeness(ctx: _Ctx, fields: ExtractedFields) -> None:
    """R2。"""
    missing = [label for name, label in REQUIRED_FIELDS if not getattr(fields, name)]
    if missing:
        ctx.hit(
            "R2",
            f"缺少{('、'.join(missing))}，无法完成后续核对",
            evidence={"missing": missing},
            tip="手动补录缺失字段后重新提交",
        )
        ctx.step(
            "check_completeness",
            "要素完整性",
            "缺号码、缺日期就没法查重也没法入账，缺了就不该往下走",
            "hit",
            result={"missing": missing},
        )
    else:
        ctx.step(
            "check_completeness",
            "要素完整性",
            "缺号码、缺日期就没法查重也没法入账，缺了就不该往下走",
            "ok",
        )


def _check_header(ctx: _Ctx, fields: ExtractedFields) -> None:
    """R3。"""
    problems: list[str] = []
    if fields.buyer_name and fields.buyer_name.strip() != COMPANY_NAME:
        problems.append(f"购买方名称为「{fields.buyer_name}」，应为「{COMPANY_NAME}」")
    if fields.buyer_tax_id and fields.buyer_tax_id.strip() != COMPANY_TAX_ID:
        problems.append(f"购买方税号为「{fields.buyer_tax_id}」，与公司登记税号不一致")

    if problems:
        ctx.hit(
            "R3",
            "；".join(problems),
            evidence={
                "expected_name": COMPANY_NAME,
                "expected_tax_id": COMPANY_TAX_ID,
                "actual_name": fields.buyer_name,
                "actual_tax_id": fields.buyer_tax_id,
            },
            citation=("P-TRAVEL", "第 8 条"),
            tip=f"联系供应商作废重开，抬头须为「{COMPANY_NAME}」",
        )
        ctx.step(
            "verify_header",
            "抬头校验",
            "购买方必须是本公司，名称或税号任一不符即驳回——这张票税务上不能入账",
            "hit",
            {"buyer_name": fields.buyer_name, "buyer_tax_id": fields.buyer_tax_id},
            {"ok": False},
        )
    else:
        ctx.step(
            "verify_header",
            "抬头校验",
            "购买方必须是本公司，名称或税号任一不符即驳回——这张票税务上不能入账",
            "ok",
            {"buyer_tax_id": fields.buyer_tax_id},
            {"ok": True},
        )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _check_deadline(ctx: _Ctx, fields: ExtractedFields) -> None:
    """R4。"""
    issued = _parse_date(fields.invoice_date)
    if issued is None:
        ctx.step(
            "check_deadline",
            "时效校验",
            f"制度给了 {DEADLINE_DAYS} 天窗口，超期不是不能报，但得有说法",
            "skip",
            {"reason": "开票日期不可解析"},
        )
        return

    days = (ctx.today - issued).days
    if days > DEADLINE_DAYS:
        ctx.hit(
            "R4",
            f"开票日期 {fields.invoice_date} 距今 {days} 天，超过 {DEADLINE_DAYS} 天提交时限",
            evidence={"days": days, "limit": DEADLINE_DAYS, "invoice_date": fields.invoice_date},
            citation=("P-TRAVEL", "第 15 条"),
            tip="补充逾期情况说明，或由部门负责人确认后提交",
        )
        ctx.step(
            "check_deadline",
            "时效校验",
            f"制度给了 {DEADLINE_DAYS} 天窗口，超期不是不能报，但得有说法",
            "hit",
            {"invoice_date": fields.invoice_date, "days": days},
            {"limit": DEADLINE_DAYS},
        )
    else:
        ctx.step(
            "check_deadline",
            "时效校验",
            f"制度给了 {DEADLINE_DAYS} 天窗口，超期不是不能报，但得有说法",
            "ok",
            {"days": days},
            {"limit": DEADLINE_DAYS},
        )


def _check_standard(ctx: _Ctx, fields: ExtractedFields) -> None:
    """R5。只对制度里写了标准的类目执行，没写的如实跳过。"""
    category = fields.category or ""
    rule = LIMITS.get(category)
    amount = fields.amount_incl_tax

    if rule is None:
        ctx.step(
            "check_standard",
            "标准核对",
            "制度只给住宿、招待、办公定了标准，这几个类目没标准可查，不硬套",
            "skip",
            {"category": category or "未识别"},
        )
        return

    limit = float(rule["limit"])
    if amount is None:
        ctx.step(
            "check_standard",
            "标准核对",
            "金额都没识别出来，没法比标准",
            "skip",
            {"category": category},
        )
        return

    if amount <= limit:
        ctx.step(
            "check_standard",
            "标准核对",
            "标准写在制度里，不是财务的心情；没超就如实放过，不制造噪音",
            "ok",
            {"category": category, "amount": amount, "limit": limit},
            {"over": 0.0},
        )
        return

    diff = round(amount - limit, 2)
    unit = rule["unit"]
    detail = f"{category} {amount:.2f} 元，超过{unit}标准 {limit:.0f} 元，差额 {diff:.2f} 元"
    if category == "住宿":
        detail += "（按 1 晚计；若实际多晚，请人工确认）"

    ctx.hit(
        "R5",
        detail,
        evidence={
            "category": category,
            "limit": limit,
            "actual": amount,
            "diff": diff,
            "unit": unit,
        },
        citation=rule["doc"],
        tip=(
            "补充部门总监的书面审批意见后重新提交"
            if category == "住宿"
            else "补充审批或调整报销金额"
        ),
    )
    ctx.step(
        "check_standard",
        "标准核对",
        f"金额明显高于{category}标准，检索条款取一个能写进结论的依据",
        "hit",
        {"category": category, "amount": amount, "limit": limit},
        {"diff": diff, "clause": f"{policy.clause(*rule['doc'])['doc_title']} {rule['doc'][1]}"},
    )


def _check_items_sum(ctx: _Ctx, fields: ExtractedFields) -> None:
    """R6。"""
    items = fields.items or []
    excl = fields.amount_excl_tax
    # excl 为 0 也要跳过：缺金额的票（R2 样例）归一化后是 0.0，
    # 拿 0 去跟明细合计比，会凭空报一条"金额勾稽不符"——那是 R2 的活，不是 R6 的。
    if not items or not excl:
        ctx.step(
            "check_items_sum",
            "明细核对",
            "总额对不上很好发现，明细对不上才是藏东西的地方",
            "skip",
            {"reason": "明细为空或缺少不含税金额"},
        )
        return

    total = round(sum(float(item.amount or 0) for item in items), 2)
    diff = round(total - float(excl), 2)
    if abs(diff) > 0.02:
        ctx.hit(
            "R6",
            f"明细合计 {total:.2f} 元，与不含税金额 {float(excl):.2f} 元相差 {diff:+.2f} 元",
            evidence={"items_total": total, "amount_excl_tax": float(excl), "diff": diff},
            tip="核对明细行是否漏录或重复录入",
        )
        ctx.step(
            "check_items_sum",
            "明细核对",
            "总额对得上不代表明细对得上，拆票、塞项目都藏在这一层",
            "hit",
            {"items": len(items), "total": total},
            {"diff": diff},
        )
    else:
        ctx.step(
            "check_items_sum",
            "明细核对",
            "总额对得上不代表明细对得上，拆票、塞项目都藏在这一层",
            "ok",
            {"items": len(items), "total": total},
            {"diff": 0.0},
        )


def _check_tax(ctx: _Ctx, fields: ExtractedFields) -> None:
    """R7。"""
    excl, tax, rate = fields.amount_excl_tax, fields.tax_amount, fields.tax_rate
    if excl is None or tax is None or rate is None:
        ctx.step(
            "check_tax",
            "税率核对",
            "税额 = 不含税 × 税率，这一步对不上，说明票面本身可疑",
            "skip",
            {"reason": "缺不含税金额、税额或税率"},
        )
        return

    rate = float(rate)
    problems: list[str] = []
    evidence: dict[str, Any] = {"rate": rate, "tax": float(tax), "amount_excl_tax": float(excl)}

    if round(rate, 4) not in LEGAL_TAX_RATES:
        problems.append(f"税率 {rate:.2%} 不在法定档位")

    # 类目与税率互相校验。只查"是不是法定档位"是不够的：
    # 13% 本身合法，但住宿服务开 13% 基本是开错了票，或者是货物冒充服务。
    category = fields.category or ""
    allowed = CATEGORY_TAX_RATES.get(category)
    if allowed and round(rate, 4) not in allowed:
        readable = " / ".join(f"{value:.0%}" for value in sorted(allowed, reverse=True))
        problems.append(
            f"{category}类发票税率 {rate:.0%} 与类目不符（{category}通常为 {readable}）"
        )

    expected = round(float(excl) * rate, 2)
    diff = round(float(tax) - expected, 2)
    evidence["expected_tax"] = expected
    evidence["diff"] = diff
    if abs(diff) > 0.05:
        problems.append(f"税额 {float(tax):.2f} 与「不含税 {float(excl):.2f} × 税率 {rate:.0%}」= {expected:.2f} 相差 {diff:+.2f}")

    if problems:
        ctx.hit(
            "R7",
            "；".join(problems),
            evidence=evidence,
            tip="核对发票税率与税额是否抄错，必要时重拍该区域",
        )
        ctx.step(
            "check_tax",
            "税率核对",
            "税额 = 不含税 × 税率，这一步对不上，说明票面本身可疑",
            "hit",
            {"rate": rate},
            {"diff": diff, "expected_tax": expected},
        )
    else:
        ctx.step(
            "check_tax",
            "税率核对",
            "税额 = 不含税 × 税率，这一步对不上，说明票面本身可疑",
            "ok",
            {"rate": rate},
            {"diff": diff},
        )


def _check_sensitive(ctx: _Ctx, fields: ExtractedFields) -> None:
    """R8。"""
    matched: list[tuple[str, float]] = []
    for item in fields.items or []:
        # 票面上的商品名常带空格或全角空格（"白 酒"），先清掉再比对，
        # 否则最该抓的那种写法反而漏掉
        name = str(item.name or "").replace(" ", "").replace("\u3000", "")
        for word in SENSITIVE_WORDS:
            if word in name:
                matched.append((word, float(item.amount or 0)))
                break

    if matched:
        word, amount = matched[0]
        ctx.hit(
            "R8",
            f"消费明细含「{word}」{amount:.2f} 元，属于需专项审批类目",
            evidence={"matched": word, "amount": amount, "all": [m[0] for m in matched]},
            citation=("P-ENTERTAIN", "第 9 条"),
            tip="补充招待事由与客户名单，并取得分管副总的书面审批",
        )
        ctx.step(
            "scan_sensitive",
            "明细扫描",
            "总额合规不代表明细合规，必须逐项看类目——烟酒娱乐是制度点名要审批的",
            "hit",
            {"items": [i.name for i in fields.items or []]},
            {"matched": word, "amount": amount},
        )
    else:
        ctx.step(
            "scan_sensitive",
            "明细扫描",
            "总额合规不代表明细合规，必须逐项看类目——烟酒娱乐是制度点名要审批的",
            "ok",
            {"items": [i.name for i in fields.items or []]},
        )


# ------------------------------------------------------------------ 结论

def _decide_verdict(hits: list[dict[str, Any]]) -> str:
    levels = {hit["level"] for hit in hits}
    if "reject" in levels:
        return "reject"
    if "manual" in levels:
        return "manual"
    if "suspect" in levels:
        return "suspect"
    return "pass"


def _headline(verdict: str, hits: list[dict[str, Any]], confidence: float) -> str:
    if verdict == "pass":
        return "要素齐全，制度核对通过"
    by_code = {hit["code"]: hit for hit in hits}
    if "R1" in by_code:
        ev = by_code["R1"]["evidence"]
        return "演示样例号码重复，与真实报销无关" if ev.get("source") in ("mock-vlm", "fixture") else "与既往审核记录号码重复，请人工核实"
    if "R3" in by_code:
        return "发票抬头不是本公司，无法入账"
    if "R0" in by_code:
        return f"识别把握只有 {confidence:.0%}，已转人工复核"
    if "R2" in by_code:
        return "关键要素没识别全，已转人工核对"
    if "R5" in by_code:
        ev = by_code["R5"]["evidence"]
        return f"超出{ev['category']}标准 {ev['diff']:.0f} 元，需审批"
    if "R8" in by_code:
        return f"含{by_code['R8']['evidence']['matched']}消费，需专项审批"
    if "R4" in by_code:
        return f"开票已 {by_code['R4']['evidence']['days']} 天，超过提交时限"
    if "R7" in by_code:
        return "税率与税额对不上，请人工核对"
    if "R6" in by_code:
        return "明细合计与票面金额不符，请人工核对"
    return "存在待确认问题，请人工复核"


def run_audit(
    fields: ExtractedFields,
    *,
    confidence: float,
    is_invoice: bool,
    history: Any,
    validation_errors: list[str] | None = None,
    today: date | None = None,
    start_step: int = 1,
) -> AuditResult:
    """一张票 → 一个结论。纯函数：不写库、不发请求，唯一的外部依赖是台账。"""
    ctx = _Ctx(start_step=start_step, today=today or date.today())

    if not is_invoice:
        ctx.hit(
            "R0",
            "这张图里没有可识别的发票，无法进入审核",
            evidence={"is_invoice": False},
        )
        ctx.step(
            "skip_rules",
            "跳过规则审核",
            "这张图里没有发票，再往下核标准、查重都没有意义——先让人确认拍的是什么",
            "skip",
            result={"reason": "is_invoice=false"},
        )
        return AuditResult(
            verdict="manual",
            hits=ctx.hits,
            citations=ctx.citations,
            trace=ctx.steps,
            headline="这张图里没有可识别的发票，已转人工",
            suggestions=["确认上传的是发票照片，而不是订单截图或聊天记录", "重新上传票面完整的照片"],
        )

    # R0 质量闸门：先判断"这份识别结果值不值得信"，再谈业务规则
    quality_issues = list(validation_errors or [])
    if confidence < settings.confidence_threshold:
        quality_issues.append(
            f"整体把握 {confidence:.0%}，低于阈值 {settings.confidence_threshold:.0%}"
        )
    if quality_issues:
        ctx.hit(
            "R0",
            "；".join(quality_issues),
            evidence={"confidence": confidence, "threshold": settings.confidence_threshold},
            tip="重拍一张：平铺、不折叠、光线均匀、四角都在画面内",
        )
        ctx.step(
            "confidence_gate",
            "置信度闸门",
            "把握不够就不让机器下结论。宁可交给人，也不给一个可能是错的答案",
            "warn",
            {"threshold": settings.confidence_threshold},
            {"confidence": confidence, "issues": quality_issues},
        )

    if _check_duplicate(ctx, fields, history):
        verdict = "reject"
        return AuditResult(
            verdict=verdict,
            hits=ctx.hits,
            citations=ctx.citations,
            trace=ctx.steps,
            headline=_headline(verdict, ctx.hits, confidence),
            suggestions=ctx.tips,
        )

    _check_completeness(ctx, fields)
    _check_header(ctx, fields)
    _check_deadline(ctx, fields)
    _check_standard(ctx, fields)
    _check_items_sum(ctx, fields)
    _check_tax(ctx, fields)
    _check_sensitive(ctx, fields)

    verdict = _decide_verdict(ctx.hits)
    ctx.step(
        "compose_verdict",
        "生成结论",
        "把命中的规则压成一个结论，并附上可以复核的依据",
        "ok" if verdict == "pass" else "hit",
        {"hits": [hit["code"] for hit in ctx.hits]},
        {"verdict": verdict},
    )

    return AuditResult(
        verdict=verdict,
        hits=ctx.hits,
        citations=ctx.citations,
        trace=ctx.steps,
        headline=_headline(verdict, ctx.hits, confidence),
        suggestions=ctx.tips,
    )