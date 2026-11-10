"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import type { PolicyAnswer } from "@/lib/types";

const SAMPLES = [
  "住宿费超标了还能报吗",
  "发票抬头写错了能报吗",
  "烟酒、礼品能报销吗",
  "出差回来多久内要交票",
  "加班费怎么算",
];

export default function AskPage() {
  const pending = useRef(false);
  const [asked, setAsked] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState<PolicyAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(question: string) {
    const text = question.trim();
    if (pending.current) return;
    if (Array.from(text).length < 2 || Array.from(text).length > 200) {
      setAsked(text);
      setData(null);
      setError("请输入 2–200 字的问题");
      return;
    }
    pending.current = true;
    setAsked(text);
    setData(null);
    setLoading(true);
    setError(null);
    try {
      setData(await api.askPolicy(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : "查询失败");
    } finally {
      pending.current = false;
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <header>
        <h1 className="text-[19px] font-semibold text-ink-900">制度问答</h1>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-500">
          只依据现行制度条款回答，每条结论都标出处。条款里没写的，它会直接说没有——
          这比编一个听起来专业的答案有用。
        </p>
      </header>

      <div className="card p-5">
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            aria-label="制度问题"
            disabled={loading}
            maxLength={200}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && ask(q)}
            placeholder="例如：住宿费超标了还能报吗"
            className="flex-1 rounded-md border border-slate-200 px-3 py-2 text-[13px] outline-none focus:border-brand-500"
          />
          <button
            onClick={() => ask(q)}
            disabled={loading}
            className="rounded-md bg-ink-900 px-4 py-2 text-[13px] font-medium text-white disabled:opacity-40"
          >
            {loading ? "查询中…" : "提问"}
          </button>
        </div>

        <p className="mt-2 text-[11px] text-ink-500">问题长度 2–200 字</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {SAMPLES.map((s) => (
            <button
              key={s}
              disabled={loading}
              onClick={() => {
                setQ(s);
                ask(s);
              }}
              className="rounded-full bg-slate-50 px-2.5 py-1 text-[11.5px] text-ink-600 ring-1 ring-slate-200 hover:bg-slate-100"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {asked && <p className="text-sm text-ink-700">本次问题：{asked}</p>}
      {error && (
        <div role="alert" className="card p-4 text-[12.5px] text-rose-700">查询失败：{error}<button className="ml-3 underline" disabled={loading} onClick={() => ask(asked)}>重试本次问题</button></div>
      )}

      {loading && (
        <div className="card space-y-3 p-5">
          <div className="skeleton h-4 w-2/3" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-4 w-4/5" />
        </div>
      )}

      {data && !loading && <AnswerCard data={data} />}
    </div>
  );
}

function AnswerCard({ data }: { data: PolicyAnswer }) {
  const tone = data.refused
    ? "amber"
    : !data.grounded
      ? "rose"
      : data.provider === "retrieval-only"
        ? "slate"
        : "emerald";

  const badge: Record<string, { text: string; cls: string }> = {
    emerald: { text: "依据条款作答", cls: "bg-emerald-50 text-emerald-700 ring-emerald-600/20" },
    amber: { text: "制度未作规定", cls: "bg-amber-50 text-amber-800 ring-amber-600/20" },
    rose: { text: "引用了不存在的条款", cls: "bg-rose-50 text-rose-700 ring-rose-600/20" },
    slate: { text: "仅返回条款原文", cls: "bg-slate-50 text-slate-600 ring-slate-300/40" },
  };

  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${badge[tone].cls}`}
        >
          {badge[tone].text}
        </span>
        <span className="text-[11px] text-ink-400">
          {data.provider === "openai-compat"
            ? `${data.model} · ${data.latency_ms}ms`
            : data.provider}
        </span>
      </div>

      <p className="mt-3 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-900">
        {data.answer}
      </p>

      {data.warning && (
        <p className="mt-3 rounded bg-rose-50 px-3 py-2 text-[11.5px] leading-relaxed text-rose-700 ring-1 ring-inset ring-rose-600/20">
          {data.warning}
        </p>
      )}

      {data.citations.length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <div className="mb-2 text-[11px] text-ink-500">依据条款</div>
          <ul className="space-y-2">
            {data.citations.map((c) => (
              <li key={`${c.doc_id}-${c.article_no}`} className="text-[12px] leading-relaxed">
                <span className="font-medium text-ink-900">
                  {c.doc_title} {c.article_no}
                </span>
                <span className="ml-1 text-ink-300">匹配度 {c.score}</span>
                <div className="mt-0.5 text-ink-600">{c.text}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-4 text-[11px] text-ink-400">
        问答只覆盖现行制度条款，不构成审批意见；有争议以财务解释为准。
      </p>
    </div>
  );
}
