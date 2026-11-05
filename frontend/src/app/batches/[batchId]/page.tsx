"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { InvoiceCard } from "@/components/InvoiceCard";
import { StatCard } from "@/components/Stats";
import { VerdictBadge } from "@/components/VerdictBadge";
import { api, assetUrl } from "@/lib/api";
import { seconds, yuan } from "@/lib/format";
import { subscribeBatch } from "@/lib/sse";
import type {
  BatchResults,
  InvoiceCard as InvoiceCardType,
  StreamBatchDone,
  StreamInvoiceDone,
} from "@/lib/types";

export default function BatchPage() {
  const params = useParams();
  const batchId = String(params.batchId ?? "");

  const [results, setResults] = useState<BatchResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [done, setDone] = useState<Record<string, StreamInvoiceDone>>({});
  const [stepLabel, setStepLabel] = useState<Record<string, string>>({});
  const [batchDone, setBatchDone] = useState<StreamBatchDone | null>(null);
  const [runId, setRunId] = useState(0);

  // 1. 先拿结果数据（决定有几张卡），再由 SSE 逐张点亮
  useEffect(() => {
    let alive = true;
    api
      .getResults(batchId)
      .then((r) => alive && setResults(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "加载失败"));
    return () => {
      alive = false;
    };
  }, [batchId]);

  // 2. 订阅审核进度流；组件卸载或重播时重连
  useEffect(() => {
    if (!results) return;
    setDone({});
    setStepLabel({});
    setBatchDone(null);

    const fallback = () => {
      // 流断了也要能用：直接把结果全部标记为完成
      const all: Record<string, StreamInvoiceDone> = {};
      results.items.forEach((i) => {
        all[i.invoice_id] = {
          invoice_id: i.invoice_id,
          verdict: i.verdict,
          headline: i.headline,
          confidence: i.confidence,
          hit_rule_codes: i.hit_rule_codes,
        };
      });
      setDone(all);
    };

    const stop = subscribeBatch(batchId, {
      onStart: (d) => setStepLabel((m) => ({ ...m, [d.invoice_id]: "开始审核" })),
      onTrace: (d) => setStepLabel((m) => ({ ...m, [d.invoice_id]: d.title })),
      onInvoiceDone: (d) => setDone((m) => ({ ...m, [d.invoice_id]: d })),
      onBatchDone: (d) => setBatchDone(d),
      onError: fallback,
    });

    return stop;
  }, [results, batchId, runId]);

  const doneCount = Object.keys(done).length;
  const total = results?.items.length ?? 0;
  const finished = Boolean(batchDone) || (total > 0 && doneCount === total);

  const elapsed = useMemo(() => {
    if (batchDone) return batchDone.elapsed_ms;
    return results?.batch.elapsed_ms ?? 0;
  }, [batchDone, results]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="card p-6">
          <h2 className="text-[15px] font-semibold text-rose-700">打不开这批数据</h2>
          <p className="mt-2 text-[12.5px] text-ink-500">{error}</p>
          <Link
            href="/"
            className="mt-4 inline-block text-[12.5px] text-brand-500 hover:text-brand-700"
          >
            ← 回到上传页
          </Link>
        </div>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 h-7 w-48 skeleton" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="card h-[190px] p-4">
              <div className="skeleton h-4 w-24" />
              <div className="mt-3 skeleton h-3 w-full" />
              <div className="mt-2 skeleton h-3 w-2/3" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const { batch } = results;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-[20px] font-semibold tracking-tight text-ink-900">
              审核结果
            </h1>
            {finished ? (
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                已完成
              </span>
            ) : (
              <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700 ring-1 ring-inset ring-brand-500/20">
                审核中 {doneCount}/{total}
              </span>
            )}
          </div>
          <p className="num mt-1 text-[11.5px] text-ink-500">
            {batch.batch_id} · {batch.created_at} · 共 {batch.invoice_count} 张 ·{" "}
            {yuan(batch.total_amount)}
          </p>
        </div>

        <button
          type="button"
          onClick={() => setRunId((r) => r + 1)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[12px] text-ink-700 transition-colors hover:border-brand-500 hover:text-brand-700"
        >
          重新播放审核过程
        </button>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="审核总数" value={String(batch.invoice_count)} hint="张" />
        <StatCard
          label="通过"
          value={String(batch.pass_count)}
          accent="emerald"
          hint="无需处理"
        />
        <StatCard
          label="存疑"
          value={String(batch.suspect_count)}
          accent="amber"
          hint="补充材料"
        />
        <StatCard
          label="驳回"
          value={String(batch.reject_count)}
          accent="rose"
          hint="不可报销"
        />
        <StatCard label="整批耗时" value={seconds(elapsed)} hint="端到端" />
      </div>

      {!finished && (
        <div className="mb-6 h-1 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-brand-500 transition-all duration-300"
            style={{ width: `${total ? (doneCount / total) * 100 : 0}%` }}
          />
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {results.items.map((item) => {
          const d = done[item.invoice_id];
          if (!d) {
            return <PendingCard key={item.invoice_id} item={item} step={stepLabel[item.invoice_id]} />;
          }
          return (
            <InvoiceCard
              key={item.invoice_id}
              item={{
                ...item,
                verdict: d.verdict,
                headline: d.headline,
                confidence: d.confidence,
                hit_rule_codes: d.hit_rule_codes,
              }}
            />
          );
        })}
      </div>

      {finished && (
        <p className="mt-6 text-center text-[12px] text-ink-300">
          审核完成。点任意一张查看字段、依据与完整轨迹。
        </p>
      )}
    </div>
  );
}

function PendingCard({ item, step }: { item: InvoiceCardType; step?: string }) {
  return (
    <div className="card overflow-hidden opacity-90">
      <div className="flex gap-3 border-b border-slate-100 p-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={assetUrl(item.image_url)}
          alt=""
          className="h-[74px] w-[54px] shrink-0 rounded border border-slate-200 bg-slate-50 object-cover grayscale"
        />
        <div className="min-w-0 flex-1">
          <VerdictBadge verdict="manual" size="sm" />
          <div className="mt-1.5 skeleton h-3.5 w-3/4" />
          <div className="mt-1.5 skeleton h-2.5 w-1/2" />
        </div>
      </div>
      <div className="p-3">
        <div className="flex items-center gap-2 text-[12px] text-ink-500">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
          {step ?? "排队中"}
          <span className="text-ink-300">…</span>
        </div>
      </div>
    </div>
  );
}
