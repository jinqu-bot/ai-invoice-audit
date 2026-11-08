"""所有接口的返回结构（= 前后端契约）。

B 只需要看这个文件 + /docs，不用问 A 任何字段问题。
改这个文件 = 改契约，必须先在群里说一声。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# pass=通过  suspect=存疑  reject=驳回  manual=转人工
Verdict = Literal["pass", "suspect", "reject", "manual"]
Level = Literal["info", "pass", "suspect", "reject", "manual"]
# warn = 这一步没出错，但结果需要人看一眼（典型场景：置信度不足，转人工）。
# 它和 error 的区别是"机器正常跑完了，只是结论不确定"，前端必须有对应样式。
TraceStatus = Literal["ok", "hit", "miss", "skip", "warn", "error"]


# ---------------------------------------------------------------- 通用

class Health(BaseModel):
    status: str = "ok"
    app: str
    version: str
    stage: str = Field(description="当前阶段，例如 D1-mock")
    recognition_provider: str = "unknown"
    demo_mode: bool
    server_time: str


class ErrorBody(BaseModel):
    code: str = Field(description="机器可读错误码，例如 BATCH_NOT_FOUND")
    message: str = Field(description="给人看的中文提示，前端可直接弹窗")


# ---------------------------------------------------------------- 批次

class BatchFailure(BaseModel):
    """这一批里没能处理的文件。以前一张失败会让整批 500，现在单独列出来。"""

    filename: str
    code: str = Field(description="机器可读原因，例如 BAD_IMAGE / EXTRACT_FAILED")
    message: str = Field(description="给人看的中文原因")


class BatchSummary(BaseModel):
    """批次卡片。上传页、历史列表都用它。"""

    batch_id: str
    created_at: str
    invoice_count: int
    status: Literal["processing", "done", "partial", "failed"] = "done"
    total_amount: float
    pass_count: int
    suspect_count: int
    reject_count: int
    manual_count: int
    elapsed_ms: int = Field(description="整批审核耗时，用于讲“30 秒”的故事")
    failed_count: int = Field(default=0, description="这一批里没处理成功的文件数")
    provider: str = Field(
        default="fixture",
        description="这一批实际用的识别来源：mock-vlm / openai-compat / mixed / fixture",
    )


class UploadResponse(BaseModel):
    batch_id: str
    invoice_count: int = Field(description="待处理/已处理张数：processing 期间是待审张数")
    created_at: str
    status: Literal["processing", "done", "partial", "failed"] = "done"
    failed: list[BatchFailure] = Field(
        default_factory=list, description="没处理成功的文件；前端要逐条显示，不要吞掉"
    )
    next_action: str = Field(description="告诉前端下一步该打哪个接口，D1 阶段防止联调走错")


class BatchList(BaseModel):
    """批次列表（D5 起分页）。"""

    total: int = Field(description="总条数，用于算分页")
    limit: int
    offset: int
    items: list["BatchSummary"] = []


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
    provider: str = "unknown"
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
    filename: str | None = Field(default=None, description="用户上传时的文件名（D5）")
    reviewed: bool = Field(
        default=False, description="是否被人工复核改判过（D8）。列表页据此打“已复核”标记"
    )
    provider: str = Field(
        default="",
        description=(
            "这张卡的数字是谁给的。`mock-vlm` 表示**演示模型**：内容和上传的图片无关，"
            "前端必须标出来，否则等于拿假数据冒充识别结果（D6 起必填）"
        ),
    )
    model: str = ""


class ReviewRecord(BaseModel):
    """一次人工复核的留痕。"""

    review_id: str
    invoice_id: str
    decided_at: str
    action: str = Field(description="复核后的结论：pass / suspect / reject / manual")
    verdict_before: str = Field(description="改判前机器给的结论")
    verdict_after: str
    reviewer: str = Field(description="谁复核的；没填就是“未登记”")
    reason: str = Field(description="凭什么改判——这一栏不能空")
    note: str = ""


class ReviewIn(BaseModel):
    """人工复核请求。理由必填，这是留痕的底线。"""

    action: Verdict = Field(description="复核后改成什么：pass / suspect / reject / manual")
    reason: str = Field(min_length=2, max_length=200, description="改判理由，至少 2 个字")
    reviewer: str = Field(default="", max_length=40, description="复核人姓名，可空")
    note: str = Field(default="", max_length=500, description="补充说明")


class InvoiceDetail(InvoiceCard):
    """详情页。在卡片基础上补全字段、规则、引用、轨迹。"""

    fields: InvoiceFields
    field_confidence: FieldConfidence
    hit_rules: list[RuleHit] = []
    citations: list[Citation] = []
    trace: list[TraceStep] = []
    suggestions: list[str] = Field(default_factory=list, description="给报销人的修改指引")
    missing_fields: list[str] = Field(
        default_factory=list,
        description=(
            "没识别出来的关键字段名。fields 里这些格子目前填的是 0 或空串"
            "（为了不让整页渲染崩），真实缺失以本字段为准——人工复核表单据此留空，不要填 0。"
        ),
    )
    reviewed: bool = Field(default=False, description="是否经过人工复核改判")
    reviews: list["ReviewRecord"] = Field(
        default_factory=list, description="人工复核轨迹，按时间正序，D8"
    )


class BatchResults(BaseModel):
    batch: BatchSummary
    items: list[InvoiceCard]
    failures: list[BatchFailure] = Field(
        default_factory=list, description="这一批没处理成功的文件（D5 起支持部分成功）"
    )


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


class PolicyAnswer(BaseModel):
    """制度问答的返回。**必须能表达"不知道"**，否则就是鼓励它编。"""

    question: str
    answer: str = Field(description="给人看的回答；降级时就是一句说明 + 条款原文")
    citations: list[Citation] = Field(default_factory=list, description="回答依据的条款")
    grounded: bool = Field(description="引用的条号是否都在检索结果里（防编造）")
    refused: bool = Field(description="制度确实没覆盖，系统选择了不答")
    provider: str = Field(description="openai-compat = 模型作答；retrieval-only = 只给原文；rules-only = 无相关条款")
    model: str = ""
    latency_ms: int = 0
    warning: str = Field(default="", description="降级或引用异常时的提示，前端要显示出来")


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


# ---------------------------------------------------------------- 抽取（D2）

class ExtractedFields(BaseModel):
    """模型直接吐出来的字段，允许为 null——看不见的字段不该被猜。"""

    invoice_code: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    seller_name: str | None = None
    seller_tax_id: str | None = None
    buyer_name: str | None = None
    buyer_tax_id: str | None = None
    amount_excl_tax: float | None = None
    tax_amount: float | None = None
    amount_incl_tax: float | None = None
    tax_rate: float | None = None
    category: str | None = None
    items: list[InvoiceItem] = []


class ValidationReport(BaseModel):
    """四道关的结果。errors 会回灌给模型重试，warnings 只提示不重试。"""

    schema_ok: bool = True
    arithmetic_ok: bool = True
    sanity_ok: bool = True
    errors: list[str] = []
    warnings: list[str] = []


class ImageMeta(BaseModel):
    sha256: str
    original_bytes: int
    compressed_bytes: int
    width: int
    height: int
    mime: str


class ExtractionResult(BaseModel):
    extraction_id: str
    is_invoice: bool
    fields: ExtractedFields
    field_confidence: FieldConfidence
    overall_confidence: float = Field(ge=0, le=1)
    verdict_hint: Verdict = Field(description="仅根据识别质量给的初判，规则引擎还没跑")
    validation: ValidationReport
    provider: str
    model: str
    cached: bool
    retry_count: int
    latency_ms: int
    image: ImageMeta
    raw_output: str | None = Field(default=None, description="模型原始输出，排错用")


# ---------------------------------------------------------------- 规则引擎（D4）

class RuleDef(BaseModel):
    """一条规则的完整定义。前端"我们怎么审的"那一页直接用，也方便评委翻。"""

    code: str = Field(description="规则编号，例如 R5")
    name: str
    level: Level = Field(description="命中后给出的结论等级")
    why: str = Field(description="这条规则为什么存在——比规则本身更值得讲")
    trigger: str = Field(description="什么情况下命中，人话")
    basis_doc: str | None = Field(default=None, description="依据的制度名")
    basis_article: str | None = Field(default=None, description="依据的条号，例如 第 12 条")
    basis_text: str | None = Field(default=None, description="条款原文，答辩时可直接念")
