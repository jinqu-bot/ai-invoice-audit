"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import type { InvoiceDetail, Verdict } from "@/lib/types";

const ACTIONS: { value: Verdict; label: string; tone: string }[] = [
  { value: "pass", label: "通过", tone: "emerald" },
  { value: "suspect", label: "存疑", tone: "amber" },
  { value: "reject", label: "驳回", tone: "rose" },
  { value: "manual", label: "转人工", tone: "indigo" },
];

const TONE: Record<string, string> = {
  pass: "bg-emerald-600 ring-emerald-600",
  suspect: "bg-amber-500 ring-amber-500",
  reject: "bg-rose-600 ring-rose-600",
  manual: "bg-indigo-600 ring-indigo-600",
};

export function ReviewPanel({
  detail,
  onUpdated,
}: {
  detail: InvoiceDetail;
  onUpdated: (next: InvoiceDetail) => void;
}) {
  const submitting = useRef(false);
  const [checked, setChecked] = useState(false);
  const [note, setNote] = useState("");
  const [success, setSuccess] = useState("");
  const [action, setAction] = useState<Verdict>(detail.verdict);
  const [reason, setReason] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reviews = detail.reviews ?? [];

  async function submit() {
    if (submitting.current) return;
    setSuccess("");
    if (!checked) { setError("请先对照原图核对关键要素"); return; }
    if (reason.trim().length < 2) {
      setError("改判必须写理由——没有理由的改判等于没留痕");
      return;
    }
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const next = await api.reviewInvoice(detail.invoice_id, {
        action,
        reason: reason.trim(),
        reviewer: reviewer.trim(),
        note: note.trim(),
      });
      onUpdated(next);
      setReason("");
      setReviewer("");
      setNote("");
      setChecked(false);
      setAction(next.verdict);
      setSuccess("复核已保存，结论及审核轨迹已更新");
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="card min-w-0 break-words p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[13.5px] font-semibold text-ink-900">人工复核</h2>
        <span className="text-[11px] text-ink-500">
          机器判错时由人改判，每次改判都留下痕迹
        </span>
      </div>

      {reviews.length > 0 && (
        <ol className="mt-3 space-y-2 border-l-2 border-slate-100 pl-3">
          {reviews.map((r) => (
            <li key={r.review_id} className="text-[11.5px] leading-relaxed [overflow-wrap:anywhere]">
              <span className="num text-ink-300">{r.decided_at}</span>
              <span className="mx-1.5 text-ink-300">·</span>
              <span className="text-ink-700">{r.reviewer}</span>
              <span className="mx-1.5 text-ink-300">·</span>
              <span className="text-ink-500">
                {ACTIONS.find(a => a.value === r.verdict_before)?.label} → <b className="text-ink-900">{ACTIONS.find(a => a.value === r.verdict_after)?.label}</b>
              </span>
              <div className="mt-0.5 whitespace-pre-wrap text-ink-700">{r.reason}</div>
              {r.note && <div className="whitespace-pre-wrap text-ink-400">{r.note}</div>}
            </li>
          ))}
        </ol>
      )}

      <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs">
        <h3 className="font-medium">对照原图核对关键要素</h3>
        <dl className="mt-2 grid gap-2 sm:grid-cols-2">
          {([["invoice_number", "发票号码"], ["invoice_date", "开票日期"], ["seller_name", "销售方"], ["buyer_name", "购买方"], ["amount_incl_tax", "价税合计"]] as const).map(([key, label]) => <div key={key} className="break-words"><dt className="text-ink-500">{label}</dt><dd className={detail.missing_fields.includes(key) ? "text-rose-700" : "text-ink-900"}>{detail.missing_fields.includes(key) ? "未识别，请核对原票并在补充说明中记录" : String(detail.fields[key])}</dd></div>)}
        </dl>
        <p className="mt-2 text-ink-500">本次保存复核结论与说明，原始识别字段不会被覆盖。若字段有误，请在说明中填写核对值。</p>
        <label className="mt-3 flex items-start gap-2"><input type="checkbox" checked={checked} disabled={busy} onChange={e => setChecked(e.target.checked)} />我已对照原图核对上述要素，并了解该记录的数据来源</label>
      </div>
      <fieldset disabled={busy} className="mt-3">
      <legend className="text-xs font-medium">选择复核结论</legend>
      <div className="mt-3 flex flex-wrap gap-2">
        {ACTIONS.map((a) => (
          <button
            key={a.value}
            type="button"
            aria-pressed={action === a.value}
            onClick={() => setAction(a.value)}
            className={[
              "min-h-11 rounded-md px-3 py-1.5 text-[12px] font-medium ring-1 transition",
              action === a.value
                ? `${TONE[a.value]} text-white`
                : "bg-white text-ink-700 ring-slate-200 hover:bg-slate-50",
            ].join(" ")}
          >
            {a.label}
          </button>
        ))}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_140px]">
        <input
          aria-label="改判理由"
          maxLength={200}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="改判理由（必填，会写进审核轨迹）"
          className="rounded-md border border-slate-200 px-3 py-1.5 text-[12px] outline-none focus:border-brand-500"
        />
        <input
          aria-label="复核人"
          maxLength={40}
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
          placeholder="复核人（可空）"
          className="rounded-md border border-slate-200 px-3 py-1.5 text-[12px] outline-none focus:border-brand-500"
        />
      </div>

      <label className="mt-3 block text-xs">补充说明 / 要素核对值（最多 500 字）
        <textarea maxLength={500} value={note} onChange={e => setNote(e.target.value)} className="mt-1 w-full rounded border border-slate-200 p-2" rows={3} />
      </label>
      </fieldset>
      {success && <p role="status" className="mt-2 text-xs text-emerald-700">{success}</p>}
      {error && <p role="alert" className="mt-2 text-[11.5px] text-rose-600">{error}。填写内容已保留；若连接中断，请先刷新核对审核轨迹，确认是否已保存，避免重复提交。</p>}

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="min-h-11 shrink-0 rounded-md bg-ink-900 px-3.5 py-1.5 text-[12px] font-medium text-white disabled:opacity-40"
        >
          {busy ? "提交中…" : "提交复核结论"}
        </button>
        <span className="text-[11px] text-ink-400">
          改判后列表页、详情页会一起变成新结论，原结论保留在轨迹里
        </span>
      </div>
    </section>
  );
}
