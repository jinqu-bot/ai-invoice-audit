/**
 * 与后端 schemas.py 一一对应的类型定义。
 * 后端改了字段，这里必须同步改——这是我们前后端唯一的"契约副本"。
 */

export type Verdict = "pass" | "suspect" | "reject" | "manual";
export type TraceStatus = "ok" | "hit" | "miss" | "skip" | "error";
export type Category = "住宿" | "餐饮" | "交通" | "办公" | "招待" | "其他";

export interface Health {
  status: string;
  app: string;
  version: string;
  stage: string;
  demo_mode: boolean;
  server_time: string;
}

export interface UploadResponse {
  batch_id: string;
  invoice_count: number;
  created_at: string;
  next_action: string;
}

export interface BatchSummary {
  batch_id: string;
  created_at: string;
  invoice_count: number;
  status: "processing" | "done" | "failed";
  total_amount: number;
  pass_count: number;
  suspect_count: number;
  reject_count: number;
  manual_count: number;
  elapsed_ms: number;
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

export interface InvoiceDetail extends InvoiceCard {
  fields: InvoiceFields;
  field_confidence: FieldConfidence;
  hit_rules: RuleHit[];
  citations: Citation[];
  trace: TraceStep[];
  suggestions: string[];
}

export interface BatchResults {
  batch: BatchSummary;
  items: InvoiceCard[];
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

export interface PolicySearchResult {
  query: string;
  clauses: PolicyClause[];
}

/** SSE 事件负载 */
export interface StreamStart {
  invoice_id: string;
  seq: number;
  total: number;
  image_url: string;
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
