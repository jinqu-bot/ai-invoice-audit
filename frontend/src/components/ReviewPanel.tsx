"use client";

import { useState } from "react";
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
  const [action, setAction] = useState<Verdict>(detail.verdict);
  const [reason, setReason] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reviews = detail.reviews ?? [];

  async function submit() {
    if (reason.trim().length < 2) {
      setError("改判必须写理由——没有理由的改判等于没留痕");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await api.reviewInvoice(detail.invoice_id, {
        action,
        reason: reason.trim(),
        reviewer: reviewer.trim(),
      });
      onUpdated(next);
      setReason("");
      setReviewer("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[13.5px] font-semibold text-ink-900">人工复核</h2>
        <span className="text-[11px] text-ink-500">
          机器判错时由人改判，每次改判都留下痕迹
        </span>
      </div>

      {reviews.length > 0 && (
        <ol className="mt-3 space-y-2 border-l-2 border-slate-100 pl-3">
          {reviews.map((r) => (
            <li key={r.review_id} className="text-[11.5px] leading-relaxed">
              <span className="num text-ink-300">{r.decided_at}</span>
              <span className="mx-1.5 text-ink-300">·</span>
              <span className="text-ink-700">{r.reviewer}</span>
              <span className="mx-1.5 text-ink-300">·</span>
              <span className="text-ink-500">
                {r.verdict_before} → <b className="text-ink-900">{r.verdict_after}</b>
              </span>
              <div className="mt-0.5 text-ink-700">{r.reason}</div>
              {r.note && <div className="text-ink-400">{r.note}</div>}
            </li>
          ))}
        </ol>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {ACTIONS.map((a) => (
          <button
            key={a.value}
            type="button"
            onClick={() => setAction(a.value)}
            className={[
              "rounded-md px-3 py-1.5 text-[12px] font-medium ring-1 transition",
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
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="改判理由（必填，会写进审核轨迹）"
          className="rounded-md border border-slate-200 px-3 py-1.5 text-[12px] outline-none focus:border-brand-500"
        />
        <input
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
          placeholder="复核人（可空）"
          className="rounded-md border border-slate-200 px-3 py-1.5 text-[12px] outline-none focus:border-brand-500"
        />
      </div>

      {error && <p className="mt-2 text-[11.5px] text-rose-600">{error}</p>}

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="rounded-md bg-ink-900 px-3.5 py-1.5 text-[12px] font-medium text-white disabled:opacity-40"
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
