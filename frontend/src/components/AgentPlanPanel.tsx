"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { AgentPlan } from "@/lib/types";

/**
 * 让模型自己决定"先查什么"（Function Calling）。
 *
 * 这是旁路：点了它不会改这张票的结论，只多一条"模型想怎么查"的轨迹。
 * 主链路的结论永远是确定性的——这一层挂了、超时了，审核照跑。
 *
 * 三件事必须在界面上说清楚，否则就成了"演 Agent"：
 * 每一步是**模型选的**还是**兜底顺序**；工具**查到了什么**；模型**在没查到时说了没有**。
 */
export function AgentPlanPanel({
  invoiceId,
  provider,
}: {
  invoiceId: string;
  provider?: string;
}) {
  const [plan, setPlan] = useState<AgentPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const realModel = provider === "openai-compat";

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setPlan(await api.planAgent(invoiceId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "调用失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card min-w-0 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[13.5px] font-semibold text-ink-900">让 AI 自己决定先查什么</h2>
        <span className="text-[11px] text-ink-500">Function Calling · 旁路，不改结论</span>
      </div>
      <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-500">
        把三个工具（查台账 / 检索制度条款 / 取费用上限）交给模型，由它决定调哪个、按什么顺序，
        每次调用的参数与返回都记在下面。模型没给出合法调用时退回固定顺序，并且会标出来。
      </p>

      {!realModel ? (
        <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[11.5px] leading-relaxed text-ink-500">
          这张票的来源是<b className="text-ink-700"> {provider || "未知"}</b>，不是真模型——
          函数调用需要真实模型，所以这里不提供演示。
          <b className="text-ink-700">模拟模型不会做规划，我们也不替它演。</b>
        </p>
      ) : (
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="mt-3 min-h-11 rounded-md bg-ink-900 px-3.5 py-1.5 text-[12px] font-medium text-white disabled:opacity-40"
        >
          {busy ? "模型正在决定…" : plan ? "再跑一次" : "让模型自己决定先查什么"}
        </button>
      )}

      {error && (
        <p role="alert" className="mt-2 text-[11.5px] text-rose-600">
          {error}
        </p>
      )}

      {plan && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-500">
            <span className="num">共 {plan.steps.length} 次工具调用</span>
            <span>·</span>
            <span className="num">{plan.rounds} 轮对话</span>
            <span>·</span>
            <span className="num">{(plan.latency_ms / 1000).toFixed(1)} 秒</span>
            <span>·</span>
            <span className="num">{plan.model || plan.provider}</span>
            {plan.fallback && (
              <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-800 ring-1 ring-inset ring-amber-600/20">
                模型未给出工具调用 · 已退回固定顺序
              </span>
            )}
          </div>

          <ol className="mt-3 space-y-2 border-l-2 border-slate-100 pl-3">
            {plan.steps.map((step) => (
              <li key={`${step.index}-${step.tool}`} className="text-[11.5px] leading-relaxed">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="num text-ink-300">{step.index}</span>
                  <span className="font-medium text-ink-900">{step.label}</span>
                  <code className="rounded bg-slate-50 px-1 py-0.5 font-mono text-[10px] text-ink-500">
                    {step.tool}
                  </code>
                  <span
                    className={[
                      "rounded px-1.5 py-0.5 text-[10px] ring-1 ring-inset",
                      step.by === "model"
                        ? "bg-brand-50 text-brand-700 ring-brand-600/20"
                        : "bg-amber-50 text-amber-800 ring-amber-600/20",
                    ].join(" ")}
                  >
                    {step.by === "model" ? "模型选择" : "兜底顺序"}
                  </span>
                  <span className="num text-[10.5px] text-ink-300">{step.latency_ms} ms</span>
                </div>
                <div className="mt-0.5 break-words text-ink-500">
                  参数 {JSON.stringify(step.args)}
                </div>
                <div className="break-words text-ink-700">
                  {String(
                    (step.result as Record<string, unknown>).note ??
                      (step.result as Record<string, unknown>).reason ??
                      JSON.stringify(step.result),
                  )}
                </div>
              </li>
            ))}
          </ol>

          <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[12px] leading-relaxed text-ink-700">
            模型判断：{plan.summary}
          </p>
          <p className="mt-1.5 text-[11px] text-ink-400">
            这只是"它想怎么查"。这张票的结论仍然来自规则引擎——那条路径是可复现、可测试的。
          </p>
        </div>
      )}
    </section>
  );
}
