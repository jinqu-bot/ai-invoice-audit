"""所有接口的返回结构（= 前后端契约）。

B 只需要看这个文件 + /docs，不用问 A 任何字段问题。
改这个文件 = 改契约，必须先在群里说一声。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# pass=通过  suspect=存疑  reject=驳回  manual=转人工
Verdict = Literal["pass", "suspect", "reject", "manual"]
Level = Literal["info", "pass", "suspect", "reject", "manual"]
TraceStatus = Literal["ok", "hit", "miss", "skip", "error"]


# ---------------------------------------------------------------- 通用

class Health(BaseModel):
    status: str = "ok"
    app: str
    version: str
    stage: str = Field(description="当前阶段，例如 D1-mock")
    demo_mode: bool
    server_time: str


class ErrorBody(BaseModel):
    code: str = Field(description="机器可读错误码，例如 BATCH_NOT_FOUND")
    message: str = Field(description="给人看的中文提示，前端可直接弹窗")


# ---------------------------------------------------------------- 批次

class BatchSummary(BaseModel):
    """批次卡片。上传页、历史列表都用它。"""

    batch_id: str
    created_at: str
    invoice_count: int
    status: Literal["processing", "done", "failed"] = "done"
    total_amount: float
    pass_count: int
    suspect_count: int
    reject_count: int
    manual_count: int
    elapsed_ms: int = Field(description="整批审核耗时，用于讲“30 秒”的故事")


class UploadResponse(BaseModel):
    batch_id: str
    invoice_count: int
    created_at: str
    next_action: str = Field(description="告诉前端下一步该打哪个接口，D1 阶段防止联调走错")


# ---------------------------------------------------------------- 发票

class InvoiceItem(BaseModel):
    name: str
    amount: float


class InvoiceFields(BaseModel):
    """一张发票被识别出来的全部要素。B 的详情页左半边就是它。"""

    invoice_code: str
    invoice_number: str
    invoice_date: str = Field(description="YYYY-MM-DD")
    seller_name: str
    seller_tax_id: str
    buyer_name: str
    buyer_tax_id: str
    amount_excl_tax: float
    tax_amount: float
    amount_incl_tax: float
    tax_rate: float = Field(description="0.06 表示 6%")
    category: Literal["住宿", "餐饮", "交通", "办公", "招待", "其他"]
    items: list[InvoiceItem] = []


class FieldConfidence(BaseModel):
    overall: float = Field(ge=0, le=1)
    per_field: dict[str, float] = Field(default_factory=dict)


class RuleHit(BaseModel):
    code: str = Field(description="规则编号，例如 R1")
    name: str
    level: Level
    detail: str = Field(description="给财务看的一句话，人话")
    evidence: dict[str, Any] | None = Field(default=None, description="命中的事实，比如历史单号")


class Citation(BaseModel):
    """制度条款引用。这是“可解释”的核心，也是答辩最容易被问的地方。"""

    doc_id: str
    doc_title: str
    article_no: str = Field(description="例如“第 12 条”")
    text: str
    score: float = Field(ge=0, le=1)


class TraceStep(BaseModel):
    """审核轨迹的一步。B 的轨迹面板按数组顺序渲染即可。"""

    step: int
    tool: str = Field(description="工具名，例如 check_duplicate")
    title: str = Field(description="中文标题，例如“查重”")
    reason: str = Field(description="为什么做这一步——这一栏是灵魂，别删")
    status: TraceStatus
    latency_ms: int
    args: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class InvoiceCard(BaseModel):
    """结果页的一张卡片。一次返回整页要的东西，B 不用再发第二次请求。"""

    invoice_id: str
    batch_id: str
    seq: int = Field(description="这一批里的第几张，用于稳定排序")
    image_url: str = Field(description="原图地址，D1 是占位 SVG")
    verdict: Verdict
    headline: str = Field(description="卡片上那句结论，例如“该发票已于 11-02 报销”")
    seller_name: str
    invoice_number: str
    invoice_date: str
    amount_incl_tax: float
    category: str
    confidence: float = Field(ge=0, le=1)
    manual_review: bool = Field(description="true 表示必须人工过一眼")
    hit_rule_codes: list[str] = []
    latency_ms: int


class InvoiceDetail(InvoiceCard):
    """详情页。在卡片基础上补全字段、规则、引用、轨迹。"""

    fields: InvoiceFields
    field_confidence: FieldConfidence
    hit_rules: list[RuleHit] = []
    citations: list[Citation] = []
    trace: list[TraceStep] = []
    suggestions: list[str] = Field(default_factory=list, description="给报销人的修改指引")


class BatchResults(BaseModel):
    batch: BatchSummary
    items: list[InvoiceCard]


# ---------------------------------------------------------------- 制度库

class PolicyDoc(BaseModel):
    doc_id: str
    title: str
    version: str
    effective_date: str
    article_count: int


class PolicyClause(BaseModel):
    doc_id: str
    doc_title: str
    article_no: str
    text: str
    score: float = Field(ge=0, le=1)


class PolicySearchResult(BaseModel):
    query: str
    clauses: list[PolicyClause]


# ---------------------------------------------------------------- 看板

class NamedCount(BaseModel):
    name: str
    count: int


class DeptAmount(BaseModel):
    dept: str
    amount: float
    count: int


class Dashboard(BaseModel):
    month: str
    total_count: int
    total_amount: float
    pass_rate: float
    reject_reasons: list[NamedCount]
    by_department: list[DeptAmount]
    by_category: list[NamedCount]
    by_supplier: list[DeptAmount]
    amount_buckets: list[NamedCount]
    daily_trend: list[NamedCount] = Field(default_factory=list, description="按日期的审核量")
