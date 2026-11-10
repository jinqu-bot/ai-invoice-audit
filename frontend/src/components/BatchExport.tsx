"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";

/** 导出原始接口证据，供按文件名对拍 GT；不在前端推算识别准确率。 */
export function BatchExport({ batchId, finished }: { batchId: string; finished: boolean }) {
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function download() {
    if (lock.current || !finished) return;
    lock.current = true; setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.getResults(batchId);
      if (result.batch.status === "processing") throw new Error("审核尚未完成，请稍后导出");
      const details = await Promise.all(result.items.map(item => api.getInvoice(item.invoice_id)));
      const payload = {
        schema_version: "invoice-audit-export/1", exported_at: new Date().toISOString(),
        notice: "原始字段及 missing_fields 用于对拍；verdict 可能已人工改判。provider/model 表示接口来源，不等于准确率。各详情按请求时读取，并非数据库事务快照。",
        batch: result.batch, failures: result.failures, invoices: details,
      };
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url;
      link.download = `audit-${batchId.replace(/[^a-zA-Z0-9_-]/g, "_")}.json`;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage(`已生成 ${details.length} 张结果、${result.failures.length} 条失败记录的下载文件`);
    } catch (e) { setError(e instanceof Error ? e.message : "导出失败，请重试"); }
    finally { lock.current = false; setBusy(false); }
  }
  return <div className="mb-5 text-xs">
    <button type="button" disabled={!finished || busy} onClick={download}
      className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 py-2 text-ink-700 disabled:opacity-40">
      {busy ? "正在准备导出…" : "导出识别明细 JSON"}
    </button>
    <p className="mt-1 text-ink-500">保留文件名、字段、缺失标记、模型来源与失败原因，供测试对拍；不含上传图片。</p>
    {message && <p role="status" className="mt-1 text-emerald-700">{message}</p>}
    {error && <p role="alert" className="mt-1 text-rose-700">{error}。未生成不完整的下载文件，可重试。</p>}
  </div>;
}
