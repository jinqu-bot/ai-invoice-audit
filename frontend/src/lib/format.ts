import type { TraceStatus, Verdict } from "./types";

/** 结论 → 文案与样式。Tailwind 必须写完整类名，不能拼接，否则会被裁掉。 */
export const VERDICT_META: Record<
  Verdict,
  { label: string; badge: string; dot: string; bar: string; soft: string }
> = {
  pass: {
    label: "通过",
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
    dot: "bg-emerald-500",
    bar: "bg-emerald-500",
    soft: "bg-emerald-50/60",
  },
  suspect: {
    label: "存疑",
    badge: "bg-amber-50 text-amber-700 ring-amber-600/20",
    dot: "bg-amber-500",
    bar: "bg-amber-500",
    soft: "bg-amber-50/60",
  },
  reject: {
    label: "驳回",
    badge: "bg-rose-50 text-rose-700 ring-rose-600/20",
    dot: "bg-rose-500",
    bar: "bg-rose-500",
    soft: "bg-rose-50/60",
  },
  manual: {
    label: "转人工",
    badge: "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
    dot: "bg-indigo-500",
    bar: "bg-indigo-500",
    soft: "bg-indigo-50/60",
  },
};

export const TRACE_STATUS_META: Record<TraceStatus, { label: string; dot: string }> = {
  ok: { label: "通过", dot: "bg-emerald-500" },
  hit: { label: "命中", dot: "bg-rose-500" },
  miss: { label: "未命中", dot: "bg-slate-300" },
  skip: { label: "跳过", dot: "bg-indigo-400" },
  warn: { label: "待确认", dot: "bg-amber-400" },
  error: { label: "异常", dot: "bg-rose-500" },
};

export const yuan = (n: number) =>
  `¥${n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

export const seconds = (ms: number) => `${(ms / 1000).toFixed(1)}s`;
