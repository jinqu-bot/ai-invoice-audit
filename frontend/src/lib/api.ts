/**
 * 后端接口封装。所有请求都从这里走，页面里不写裸 fetch。
 */

import type {
  BatchList,
  BatchResults,
  Dashboard,
  Health,
  InvoiceDetail,
  PolicyAnswer,
  PolicySearchResult,
  RuleDef,
  UploadResponse,
} from "./types";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

/** 后端返回的是相对路径，拼成可直接放进 <img src> 的绝对地址 */
export function assetUrl(path: string): string {
  if (!path) return "";
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError("连接中断或无法连接服务，请检查后端和网络后重试", 0);
  }
  if (!res.ok) {
    let message = `请求失败（HTTP ${res.status}）`;
    try {
      const body = (await res.json()) as { message?: string; detail?: string; details?: { field: string; reason: string }[] };
      message = typeof body.message === "string" ? body.message : typeof body.detail === "string" ? body.detail : message;
      if (Array.isArray(body.details)) message += `：${body.details.map((d) => `${d.field} ${d.reason}`).join("；")}`;
    } catch {
      // 忽略解析失败，用默认文案
    }
    throw new ApiError(message, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),

  /** 演示模式上传：不发文件，后端直接返回演示批次 */
  uploadDemo: () => request<UploadResponse>("/api/batches?demo=true", { method: "POST" }),

  /** 上传文件；识别来源由后端配置决定，结果页读取 batch.provider。 */
  uploadFiles: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<UploadResponse>("/api/batches", { method: "POST", body: form });
  },

  getResults: (batchId: string) =>
    request<BatchResults>(`/api/batches/${encodeURIComponent(batchId)}/results`),

  /** 批次列表（D5 起分页，返回 {total, items} 而不是数组） */
  listBatches: (limit = 20, offset = 0) =>
    request<BatchList>(`/api/batches?limit=${limit}&offset=${offset}`),

  getRules: () => request<RuleDef[]>("/api/rules"),

  getInvoice: (invoiceId: string) =>
    request<InvoiceDetail>(`/api/invoices/${encodeURIComponent(invoiceId)}`),

  /** 人工复核改判（D8）：理由必填，后端会留痕 */
  reviewInvoice: (
    invoiceId: string,
    payload: { action: string; reason: string; reviewer?: string; note?: string },
  ) =>
    request<InvoiceDetail>(`/api/invoices/${encodeURIComponent(invoiceId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getDashboard: (month?: string) =>
    request<Dashboard>(`/api/dashboard${month ? `?month=${month}` : ""}`),

  searchPolicies: (q: string) =>
    request<PolicySearchResult>(`/api/policies/search?q=${encodeURIComponent(q)}`),

  /** 制度问答（D8）：只依据条款回答，答不出来会 refused=true */
  askPolicy: (q: string) =>
    request<PolicyAnswer>(`/api/policies/ask?q=${encodeURIComponent(q)}`),
};

/** 当前演示批次号，页面上"看演示数据"直接跳它 */
export const DEMO_BATCH_ID = "B20261104-001";
