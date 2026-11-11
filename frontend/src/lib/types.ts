/**
 * 与后端 schemas.py 一一对应的类型定义。
 * 后端改了字段，这里必须同步改——这是我们前后端唯一的"契约副本"。
 */

export type Verdict = "pass" | "suspect" | "reject" | "manual";
/** warn = 跑完了但需要人看一眼（如置信度不足转人工），不是报错，必须有样式 */
export type TraceStatus = "ok" | "hit" | "miss" | "skip" | "warn" | "error";
export type Category = "住宿" | "餐饮" | "交通" | "办公" | "招待" | "其他";

export interface Health {
  status: string;
  app: string;
  version: string;
  stage: string;
  demo_mode: boolean;
  recognition_provider?: string;
  server_time: string;
}

export interface UploadResponse {
  batch_id: string;
  invoice_count: number;
  created_at: string;
  /**
   * processing = 后端已接单，正在后台逐张审（D6 起上传默认是它，HTTP 202）
   * partial = 有文件没处理成功；failed = 一个都没成功；done = 全好了
   */
  status: "processing" | "done" | "partial" | "failed";
  /** 没处理成功的文件，必须逐条显示，别吞掉 */
  failed: BatchFailure[];
  next_action: string;
}

export interface BatchFailure {
  filename: string;
  code: string;
  message: string;
}

export interface BatchSummary {
  batch_id: string;
  created_at: string;
  invoice_count: number;
  status: "processing" | "done" | "partial" | "failed";
  total_amount: number;
  pass_count: number;
  suspect_count: number;
  reject_count: number;
  manual_count: number;
  elapsed_ms: number;
  /** 这一批没处理成功的文件数（D5） */
  failed_count: number;
  /** mock-vlm / openai-compat / mixed / fixture；mock-vlm 时页面上要标"演示模式" */
  provider: string;
}

export interface BatchList {
  total: number;
  limit: number;
  offset: number;
  items: BatchSummary[];
}

/** 规则清单（GET /api/rules），"我们怎么审的"那一页直接用 */
export interface RuleDef {
  code: string;
  name: string;
  level: Verdict | "info";
  why: string;
  trigger: string;
  basis_doc: string | null;
  basis_article: string | null;
  basis_text: string | null;
}

export interface InvoiceCard {
  invoice_id: string;
  batch_id: string;
  seq: number;
  image_url: string;
  verdict: Verdict;
  headline: string;
  seller_name: string;
  invoice_number: string;
  invoice_date: string;
  amount_incl_tax: number;
  category: string;
  confidence: number;
  manual_review: boolean;
  hit_rule_codes: string[];
  latency_ms: number;
  /** 用户上传时的原始文件名（D5） */
  filename?: string | null;
  /**
   * 这张卡的数字是谁给的。`mock-vlm` = 演示模型：内容与上传的图片无关，
   * 页面上必须标出来，否则等于拿编出来的数据冒充识别结果。
   */
  provider?: string;
  model?: string;
  /** 这次结论直接取自识别缓存，没有真的调模型。几毫秒出结果不等于模型变快了 */
  cached?: boolean;
}

export interface InvoiceItem {
  name: string;
  amount: number;
}

export interface InvoiceFields {
  invoice_code: string;
  invoice_number: string;
  invoice_date: string;
  seller_name: string;
  seller_tax_id: string;
  buyer_name: string;
  buyer_tax_id: string;
  amount_excl_tax: number;
  tax_amount: number;
  amount_incl_tax: number;
  tax_rate: number;
  category: Category;
  items: InvoiceItem[];
}

export interface FieldConfidence {
  overall: number;
  per_field: Record<string, number>;
}

export interface RuleHit {
  code: string;
  name: string;
  level: Verdict | "info";
  detail: string;
  evidence?: Record<string, unknown> | null;
  /** 这一条命中依据的制度条款。制度没写的规则为 null，不要自己补 */
  basis_doc?: string | null;
  basis_article?: string | null;
  basis_text?: string | null;
}

export interface Citation {
  doc_id: string;
  doc_title: string;
  article_no: string;
  text: string;
  score: number;
}

export interface TraceStep {
  step: number;
  tool: string;
  title: string;
  reason: string;
  status: TraceStatus;
  latency_ms: number;
  args?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
}

export interface ReviewRecord {
  review_id: string;
  invoice_id: string;
  decided_at: string;
  action: string;
  verdict_before: string;
  verdict_after: string;
  reviewer: string;
  reason: string;
  note: string;
}

export interface InvoiceDetail extends InvoiceCard {
  fields: InvoiceFields;
  field_confidence: FieldConfidence;
  hit_rules: RuleHit[];
  citations: Citation[];
  trace: TraceStep[];
  suggestions: string[];
  /** 没识别出来的关键字段名。fields 里对应格子是 0/空串，人工复核表单应据此留空 */
  missing_fields: string[];
  /** 是否被人工复核改判过（D8） */
  reviewed?: boolean;
  /** 人工复核轨迹，按时间正序 */
  reviews?: ReviewRecord[];
}

export interface BatchResults {
  batch: BatchSummary;
  items: InvoiceCard[];
  /** 这一批没处理成功的文件（D5 起支持部分成功） */
  failures: BatchFailure[];
}

export interface NamedCount {
  name: string;
  count: number;
}

export interface DeptAmount {
  dept: string;
  amount: number;
  count: number;
}

export interface Dashboard {
  month: string;
  total_count: number;
  total_amount: number;
  pass_rate: number;
  reject_reasons: NamedCount[];
  by_department: DeptAmount[];
  by_category: NamedCount[];
  by_supplier: DeptAmount[];
  amount_buckets: NamedCount[];
  daily_trend: NamedCount[];
  /** db=库里真审核过的票；fixture=空库退回的演示样例（页面必须标出来） */
  source?: "db" | "fixture";
}

export interface PolicyDoc {
  doc_id: string;
  title: string;
  version: string;
  effective_date: string;
  article_count: number;
}

export interface PolicyClause {
  doc_id: string;
  doc_title: string;
  article_no: string;
  text: string;
  score: number;
}

export interface PolicyAnswer {
  question: string;
  answer: string;
  citations: Citation[];
  grounded: boolean;
  refused: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  warning: string;
}

export interface PolicySearchResult {
  query: string;
  clauses: PolicyClause[];
}

/** SSE 事件负载 */

/** D6：一上来先告诉你这批一共有几张，页面可以立刻摆好骨架屏 */
export interface StreamHello {
  batch_id: string;
  /** true = 这批已经跑完，是回放；false = 正在发生 */
  replay: boolean;
}

export interface StreamBatchStart {
  batch_id: string;
  total: number;
  failed: number;
}

export interface StreamStart {
  invoice_id: string;
  seq: number;
  total: number;
  image_url: string;
  filename?: string;
}

/** D6：文件级失败当场推送，带原因 */
export interface StreamFileFailed {
  filename: string;
  code: string;
  message: string;
}

export interface StreamTrace {
  invoice_id: string;
  step: number;
  tool: string;
  title: string;
  reason: string;
  status: TraceStatus;
  latency_ms: number;
}

export interface StreamInvoiceDone {
  invoice_id: string;
  verdict: Verdict;
  headline: string;
  confidence: number;
  hit_rule_codes: string[];
}

export interface StreamBatchDone {
  batch_id: string;
  elapsed_ms: number;
  summary: BatchSummary;
}
